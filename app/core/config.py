from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Which provider app/core/llm_provider.py builds. "groq" or "azure".
    llm_provider: str = "groq"

    # Optional so that the app starts when the other provider is selected.
    # A missing key for the ACTIVE provider is raised by llm_provider.py at
    # first use, naming the setting, rather than failing at import.
    groq_api_key: Optional[str] = None

    embedding_model: str = "all-MiniLM-L6-v2"
    model_name: str = "openai/gpt-oss-20b"

    # Azure OpenAI. The deployment is the name chosen when the resource was
    # provisioned and is frequently NOT the model name. A wrong value here
    # returns a 404 that reads like a model problem.
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_deployment: Optional[str] = None
    azure_openai_api_version: str = "2024-10-21"

    # Set true when the deployment is a reasoning model (GPT-5 series,
    # o-series), which rejects max_tokens and requires
    # max_completion_tokens on the Chat Completions API.
    azure_openai_uses_completion_tokens: bool = False

    # Leave unset for a reasoning deployment: those reject any temperature
    # but the default, so the parameter is omitted from the request rather
    # than sent as 0. Set a number only for an ordinary chat deployment.
    azure_openai_temperature: Optional[float] = None

    # Optional: "minimal", "low", "medium", "high". Higher costs more
    # tokens and more latency, which matters at screening volume.
    azure_openai_reasoning_effort: Optional[str] = None

    # B21 (FinOps): explicit per-1M-token rates for this deployment. Unset
    # by default — app/core/pricing.py falls back to a bundled retail
    # estimate rather than assuming $0, which would make every cost figure
    # on web/developer.html read as free.
    azure_openai_input_cost_per_1m: Optional[float] = None
    azure_openai_output_cost_per_1m: Optional[float] = None

    # Email (optional - only needed for send feature)
    smtp_host: str     = "smtp.gmail.com"
    smtp_port: int     = 465
    sender_email: str  = ""
    sender_password: str = ""
    company_name: str  = "Our Company"

    # B10: "simulated" (default) records the message and transmits nothing —
    # identical to the product's behavior before this setting existed. Only
    # "outlook" attempts a real send, through a local signed-in Outlook
    # desktop profile via app.core.outlook_adapter. Same opt-in shape as
    # QUEUE_BACKEND: a real shell/env value, never flipped on by a stored
    # default, because "outlook" has not been exercised against a live
    # mailbox in this environment.
    email_backend: str = "simulated"

    # B10: the Outlook account a real send goes out from. Mirrors
    # `calendar_sender_email` below — same reason: Outlook's default account
    # is whichever profile happens to be primary on this machine, which is
    # not necessarily the identity the product should send as. Empty means
    # "whatever Outlook picks", exactly as before this setting existed.
    email_sender_address: str = ""

    # B11: same opt-in shape as email_backend, but a separate flag — a
    # calendar invite is a different Outlook COM item (AppointmentItem, not
    # MailItem) and a site may want one integration live before the other.
    # "outlook" attempts a real invite through app.core.calendar_adapter.
    calendar_backend: str = "simulated"
    calendar_sender_email: str = ""

    # B10/B11: whether a reply's classified signal is auto-applied through an
    # existing service call (a hiring manager's PROCEED/DECLINE/QUESTION
    # verdict only — see app/services/reply_service.py) or only ever recorded
    # as a proposed decision for a person to apply by hand. Off by default,
    # same opt-in shape as email_backend/calendar_backend: reply ingestion
    # itself is already gated on email_backend == "outlook", and this is a
    # second, separate gate on top of that for what happens once a reply is
    # read, not a substitute for it.
    auto_apply_reply_decisions: bool = False

    # B22 phase 1: signs the login session token (app/core/session_auth.py).
    # A stateless HMAC secret, not a per-user password store — change this
    # to invalidate every signed-in session at once (e.g. after a leak).
    session_secret: str = "dev-only-change-me"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
