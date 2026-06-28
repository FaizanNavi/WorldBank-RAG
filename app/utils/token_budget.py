import tiktoken
import json
import logging
logger = logging.getLogger(__name__)
class TokenBudgetManager:
    def __init__(self, max_tokens=4000):
        self.max_tokens = max_tokens
        try:
            self.encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.encoder = None
            logger.warning("tiktoken not available, using rough estimation")
    def count_tokens(self, text: str) -> int:
        if self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4
    def trim_context(self, system_prompt: str, tool_results: list, query: str) -> list:
        fixed_tokens = self.count_tokens(system_prompt) + self.count_tokens(query) + 100
        available = self.max_tokens - fixed_tokens
        if available <= 0:
            logger.warning("System prompt + query alone exceed token budget!")
            return []
        trimmed = []
        used = 0
        for result in tool_results:
            result_text = json.dumps(result) if isinstance(result, dict) else str(result)
            result_tokens = self.count_tokens(result_text)
            if used + result_tokens > available:
                compressed = self._compress_result(result)
                compressed_tokens = self.count_tokens(json.dumps(compressed))
                if used + compressed_tokens <= available:
                    trimmed.append(compressed)
                    used += compressed_tokens
                else:
                    logger.info(f"Dropping tool result - over budget ({used}/{available} tokens)")
                    break
            else:
                trimmed.append(result)
                used += result_tokens
        logger.info(f"Token budget: {used}/{available} tokens used ({len(trimmed)}/{len(tool_results)} results kept)")
        return trimmed
    def _compress_result(self, result):
        if isinstance(result, dict) and "data" in result:
            data = result["data"]
            if isinstance(data, list) and len(data) > 10:
                compressed = result.copy()
                compressed["data"] = data[:10]
                compressed["_note"] = f"Compressed from {len(data)} to 10 data points"
                return compressed
        return result
