import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Index
from sqlalchemy.orm import validates
from app.core.database import Base

# Gateways whose payments are confirmed by a signed callback (never sandbox / manual). Only
# Kashier (EGP and USD) takes new payments; "stripe" and "paymob" only cover records made before
# Kashier replaced them (no checkout and no webhook use them any more), so an admin can settle them.
GATEWAY_PROVIDERS = ("kashier", "stripe", "paymob")
# A gateway payment in these states is unresolved: money may still be taken for it, so the
# account may not start another one until it is confirmed paid / failed (or resolved by an admin).
OPEN_STATUSES = ("pending", "review")


class Payment(Base):
    """
    A checkout attempt (plan subscription or add-on exam pack) by a lecturer account.

    status:
      pending        created, waiting for the gateway's signed confirmation
      review         still pending after 24h: needs reconciliation by an admin (never "failed")
      paid           confirmed by the gateway (or sandbox / admin) and applied once
      failed         confirmed not paid (declined, expired, mismatch) — a new checkout is allowed
      refunded       the gateway (or an admin) confirmed the money was returned; entitlement removed
      refund_review  a partial / unclear refund was reported: kept for an admin to decide
    """
    __tablename__ = "payments"
    __table_args__ = (
        # At most one unresolved gateway payment per account, even under concurrent checkouts.
        Index("ux_payments_one_open", "user_id", "open_slot", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(64), unique=True, index=True, default=lambda: f"oiq_{uuid.uuid4().hex}")
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    kind = Column(String(16), default="plan")      # plan | addon
    plan_id = Column(String(32), nullable=True)
    period = Column(String(16), nullable=True)     # monthly | term | yearly
    addon_exams = Column(Integer, default=0)

    amount = Column(Integer)                       # whole currency units (EGP / USD)
    currency = Column(String(8), default="EGP")
    provider = Column(String(16))                  # kashier | sandbox | manual (stripe, paymob: legacy)
    status = Column(String(16), default="pending", index=True)
    provider_txn_id = Column(String(128), nullable=True, index=True)
    # The gateway's order (Kashier "kashier_order:<kashierOrderId>"):
    # kept after payment so a later refund / void callback maps back to this payment.
    provider_order_ref = Column(String(128), nullable=True, index=True)
    # 1 while unresolved at a gateway, NULL otherwise (kept by _track_open; see the index above).
    open_slot = Column(Integer, nullable=True)
    checkout_url = Column(Text, nullable=True)     # returned again on a repeated click while valid
    checkout_expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    review_at = Column(DateTime, nullable=True)    # when it moved to review (pending > 24h)
    refunded_at = Column(DateTime, nullable=True)
    refunded_amount_minor = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)

    @validates("status", "provider")
    def _track_open(self, key, value):
        status = value if key == "status" else self.status
        provider = value if key == "provider" else self.provider
        is_open = (status or "pending") in OPEN_STATUSES and provider in GATEWAY_PROVIDERS
        self.open_slot = 1 if is_open else None
        return value
