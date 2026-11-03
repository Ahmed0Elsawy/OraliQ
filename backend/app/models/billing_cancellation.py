from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from app.core.database import Base


class BillingCancellationRequest(Base):
    """
    A lecturer's cancellation request, received by e-mail at OralIQ support and recorded by an
    admin. The arrival time is typed in by the admin from the e-mail itself — nothing here reads a
    mailbox. Nothing here moves money either: a refund is approved and carried out by a person.

    Recording the request pauses the lecturer's service at once (subscription, add-on exam balance,
    creating exams). What was left of it when the
    e-mail ARRIVED is saved (remaining_seconds), so neither the time until it was recorded nor the
    admin's review time counts against the lecturer:
      * resolved (the lecturer stays)  -> the subscription comes back with that remaining time
      * approved (cancel for good)     -> refund = amount paid for the term × remaining / term length
                                          (no fees, taxes or deductions), carried out by hand later

    Three separate times, never derived from one another:
      request_received_at  when the e-mail arrived — fixed at creation, never changed
      decided_at           when the admin resolved it or approved the refund
      refund_executed_at   when the refund was actually carried out (as recorded)

    status: open (paused) | resolved (reactivated) | approved (refund approved) | refunded
    All times are naive UTC, like the rest of this database.
    """
    __tablename__ = "billing_cancellation_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)   # the paying lecturer
    channel = Column(String(16), nullable=False, default="email")
    request_received_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)          # = when it was paused
    recorded_by = Column(Integer, nullable=True)

    # The subscription as it was when the e-mail arrived.
    plan_tier_at_request = Column(String(32), nullable=True)
    plan_period_at_request = Column(String(16), nullable=True)
    plan_started_at_at_request = Column(DateTime, nullable=True)
    plan_expires_at_at_request = Column(DateTime, nullable=True)
    cycle_started_at_at_request = Column(DateTime, nullable=True)
    cycle_exams_used_at_request = Column(Integer, nullable=True)
    # Add-on exam balance frozen while the request is open (the account's balance is set to 0 and
    # nothing can be consumed); given back in full if the lecturer stays.
    bonus_exams_frozen = Column(Integer, nullable=False, default=0)
    remaining_seconds = Column(Integer, nullable=False, default=0)    # left at request_received_at
    # The paid term behind it (plan payments since the plan started): length, amount, currency.
    term_seconds = Column(Integer, nullable=True)
    term_paid_minor = Column(Integer, nullable=True)
    term_currency = Column(String(8), nullable=True)
    term_payment_ids = Column(Text, nullable=True)                    # comma-separated Payment ids
    computed_refund_minor = Column(Integer, nullable=True)            # None: needs a person (see note)

    status = Column(String(16), nullable=False, default="open", index=True)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(Integer, nullable=True)
    decision_note = Column(Text, nullable=True)
    reactivated_at = Column(DateTime, nullable=True)
    reactivated_until = Column(DateTime, nullable=True)
    refund_amount_minor = Column(Integer, nullable=True)
    refund_currency = Column(String(8), nullable=True)

    refund_executed_at = Column(DateTime, nullable=True)
    refund_recorded_by = Column(Integer, nullable=True)
    refund_reference = Column(String(128), nullable=True)
    note = Column(Text, nullable=True)
