"""Middleware attributing local API requests to an assistant conversation.

The assistant's ``call_kiln_api`` tool stamps ``X-Kiln-Conversation-Id`` on the
requests it makes to this server. This middleware reads that header into the
``spend_ledger.current_conversation_id`` contextvar for the duration of the
request, so model runs executed while handling it (task runs, evals, judges,
data gen) credit the conversation's spend ledger — see
``spend_ledger.record_spend_for_current_conversation``, called from the LiteLLM
adapter per LLM call.

Requests without the header (everything user-initiated) leave the contextvar
unset and are never budget-tracked.
"""

from kiln_ai.utils import spend_ledger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class BudgetContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        conversation_id = request.headers.get(spend_ledger.CONVERSATION_ID_HEADER)
        if conversation_id is None or not spend_ledger.is_valid_conversation_id(
            conversation_id
        ):
            return await call_next(request)

        token = spend_ledger.current_conversation_id.set(conversation_id)
        try:
            return await call_next(request)
        finally:
            spend_ledger.current_conversation_id.reset(token)
