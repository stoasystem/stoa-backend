# v5.19 Research: Pitfalls

## Pitfalls

- Reusing web localStorage/token assumptions in native. Native must use Amplify session handling and secure storage boundaries instead.
- Porting the full web UI literally, which would produce awkward mobile flows and hide the highest-risk native behaviors.
- Claiming push readiness without real device evidence, Expo project IDs, FCM/APNs credentials, or EAS build context.
- Adding offline mutations for quota-consuming flows. This can duplicate usage ledger events, bypass entitlement checks, or create reconciliation drift.
- Caching private learning content, raw report artifacts, provider payloads, billing payloads, or Cognito token material.
- Treating "Forbidden" or "Unauthorized" as acceptable mobile UX for account-state problems that already have support-safe explanations.
- Making deep links trust notification payloads. Routes must still pass auth, role, and entitlement checks.
- Storing sensitive state in a persistence layer that survives user switch or sign-out.
- Assuming app-store launch is the same as internal mobile readiness. Store policies, screenshots, privacy labels, signing, and review can become separate release work.
- Letting SDK versions drift during implementation. React Native, Expo, Xcode, Android target SDK, and EAS behavior are moving targets.

## Prevention

- Centralize auth/session and API token handling in one native service.
- Define a mobile route and feature matrix before coding broad UI coverage.
- Use EAS/internal builds and physical-device smoke as release evidence.
- Keep offline scope read-only unless a separate quota-safe mutation design is approved.
- Add cache redaction and sign-out clearing tests.
- Map backend support-safe error codes to explicit mobile messages.
- Validate deep-link targets after session restore and role/account-state checks.
- Record provider/app-store blockers rather than hiding them behind generic "mobile complete" language.
