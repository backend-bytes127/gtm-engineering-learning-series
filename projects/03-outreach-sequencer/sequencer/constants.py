"""Names and limits shared across the sequencer. Nothing here changes at run time."""

from __future__ import annotations

# --- channels (the step model is borrowed from outbound-os: email, LinkedIn invite, LinkedIn message) ---
EMAIL = "email"
LINKEDIN_INVITE = "linkedin_invite"
LINKEDIN_MESSAGE = "linkedin_message"
CHANNELS = (EMAIL, LINKEDIN_INVITE, LINKEDIN_MESSAGE)
GROUP_EMAIL = "email"
GROUP_LINKEDIN = "linkedin"
CHANNEL_GROUP = {EMAIL: GROUP_EMAIL, LINKEDIN_INVITE: GROUP_LINKEDIN, LINKEDIN_MESSAGE: GROUP_LINKEDIN}

# --- contact status (the five from the brief, plus Stopped for bounces and opt-outs) ---
NOT_STARTED = "Not Started"
IN_SEQUENCE = "In Sequence"
REPLIED = "Replied"
MEETING_BOOKED = "Meeting Booked"
COMPLETED = "Completed"
STOPPED = "Stopped"
STATUSES = (NOT_STARTED, IN_SEQUENCE, REPLIED, MEETING_BOOKED, COMPLETED, STOPPED)
ACTIVE_STATUSES = (IN_SEQUENCE,)

# --- events recorded against a contact (a touch is what we do; an event is what happens next) ---
OPENED = "opened"
ACCEPTED = "accepted"
REPLY = "replied"
BOUNCED = "bounced"
MEETING = "meeting_booked"
UNSUBSCRIBED = "unsubscribed"
EVENT_KINDS = (OPENED, ACCEPTED, REPLY, BOUNCED, MEETING, UNSUBSCRIBED)
# Stop rules a user may switch off. Unsubscribe always stops the contact: that is a legal requirement, not a preference.
STOP_RULE_KINDS = (REPLY, BOUNCED, MEETING)

# --- touch outcomes ---
SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"

# --- stop reasons ---
REASON_BOUNCED = "bounced"
REASON_OPTED_OUT = "opted_out"
REASON_DRAFT_INCOMPLETE = "draft_incomplete"

# --- validation reasons (why a record was removed or changed) ---
INVALID_EMAIL = "invalid_email"
INVALID_LINKEDIN = "invalid_linkedin_url"
NO_CHANNEL = "no_reachable_channel"
DUPLICATE = "duplicate"
OPTED_OUT = "opted_out"
MISSING_NAME = "missing_name"

# --- limits (LinkedIn caps are deliberately conservative; the sending rules can lower them, never raise them) ---
MAX_STEPS = 10
MAX_WAIT_DAYS = 60
HARD_CAP_EMAIL_PER_DAY = 200
HARD_CAP_INVITES_PER_DAY = 25
HARD_CAP_MESSAGES_PER_DAY = 100
LINKEDIN_INVITE_MAX_CHARS = 300
INVITE_EXPIRY_DAYS = 14  # an invite not accepted by then is treated as lost, and the follow-up DM is skipped
