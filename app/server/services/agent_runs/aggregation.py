from __future__ import annotations


###############################################################################
class AggregatedRequestService:
    # -------------------------------------------------------------------------
    def build_aggregated_request(
        self,
        original_request: str,
        steering_messages: list[str],
    ) -> str:
        normalized_messages = [
            item.strip() for item in steering_messages if item.strip()
        ]
        if not normalized_messages:
            return original_request
        steering_block = "\n".join(
            f"{index}. {message}"
            for index, message in enumerate(normalized_messages, start=1)
        )
        return (
            "Original request:\n"
            f"{original_request}\n\n"
            "User steering received while the run was active:\n"
            f"{steering_block}\n\n"
            "Current effective request:\n"
            "Satisfy the original request while applying all steering messages above. "
            "Later steering supersedes earlier steering only where they conflict."
        )
