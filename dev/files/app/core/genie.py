"""Ask AI backed by a Databricks Genie Agent, called through the Conversation API as the signed-in viewer."""

import time
from typing import Callable

import pandas as pd

from core.assistant import Answer, Step
from core.data import QueryError, sql_client

POLL_SECONDS = 1.5
TIMEOUT_SECONDS = 180
FINISHED = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}
STATUS_LABELS = {
    "SUBMITTED": "Sent to Genie",
    "FILTERING_CONTEXT": "Picking the relevant tables",
    "ASKING_AI": "Writing SQL",
    "PENDING_WAREHOUSE": "Waking up the SQL warehouse",
    "EXECUTING_QUERY": "Running the query",
}
_NUMERIC = {"BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "DECIMAL"}

REAUTH_MESSAGE = (
    "SESSION_NEEDS_REAUTH: your sign-in to this app was approved before it could use Genie. Open the app in a "
    "private/incognito window (or clear cookies for databricksapps.com), sign in again and accept the prompt."
)


def _value(enum_or_str) -> str:
    return getattr(enum_or_str, "value", enum_or_str) or ""


def _frame(response) -> pd.DataFrame:
    statement = response.statement_response
    manifest = statement.manifest if statement else None
    columns = manifest.schema.columns if manifest and manifest.schema else []
    rows = statement.result.data_array if statement and statement.result and statement.result.data_array else []
    df = pd.DataFrame(rows, columns=[c.name for c in columns])
    for column in columns:
        if _value(column.type_name) in _NUMERIC:
            df[column.name] = pd.to_numeric(df[column.name], errors="coerce")
    return df


def ask_genie(
    question: str,
    space_id: str,
    conversation_id: str | None = None,
    on_status: Callable[[str], None] | None = None,
) -> tuple[Answer, str]:
    """Send a question (or a follow-up in an existing conversation) to Genie and wait for the answer.

    Returns the answer (text + one Step per SQL query Genie ran) and the conversation id for follow-ups."""
    w = sql_client()  # the viewer's identity: Unity Catalog grants apply, and usage isn't billed to the app
    try:
        if conversation_id:
            sent = w.genie.create_message(space_id, conversation_id, question).response
            message_id = getattr(sent, "message_id", None) or sent.id
        else:
            sent = w.genie.start_conversation(space_id, question).response
            conversation_id, message_id = sent.conversation_id, sent.message_id
    except Exception as exc:
        if "scope" in str(exc).lower():
            raise QueryError(REAUTH_MESSAGE) from exc
        raise

    deadline = time.time() + TIMEOUT_SECONDS
    reported = None
    while True:
        message = w.genie.get_message(space_id, conversation_id, message_id)
        status = _value(message.status)
        if status in FINISHED:
            break
        if status != reported and on_status:
            on_status(STATUS_LABELS.get(status, status.replace("_", " ").capitalize()))
            reported = status
        if time.time() > deadline:
            raise QueryError(f"Genie didn't answer within {TIMEOUT_SECONDS} seconds.")
        time.sleep(POLL_SECONDS)

    if status != "COMPLETED":
        detail = message.error.error if message.error and message.error.error else status
        raise QueryError(f"Genie couldn't answer: {detail}")

    texts, steps = [], []
    for attachment in message.attachments or []:
        if attachment.text and attachment.text.content:
            texts.append(attachment.text.content)
        if attachment.query and attachment.query.query:
            step = Step("genie", {}, attachment.query.description or "Genie query", sql=attachment.query.query)
            try:
                step.result = _frame(w.genie.get_message_attachment_query_result(
                    space_id, conversation_id, message_id, attachment.attachment_id))
            except Exception as exc:  # the answer text is still useful without the rows
                step.error = str(exc)
            steps.append(step)

    text = "\n\n".join(texts) or ("Here's the result." if steps else "Genie didn't return an answer.")
    return Answer(text, steps), conversation_id
