# Deferred Items

## 476-03

- Removing the forbidden `SubscriptionTier.FREE`, `.STANDARD`, and `.PREMIUM`
  aliases exposes legacy references in `src/stoa/services/entitlement_service.py`
  and `src/stoa/services/subscription_service.py`; importing the legacy entitlement
  service currently raises `AttributeError` before its later canonical migration.
  Adding aliases or translating the new product IDs back to daily request-count
  tiers would violate D-02 and Plan 476-03. Plans 476-12 and 476-14 explicitly own
  the paid-grant and free-trial entitlement migrations, respectively.
