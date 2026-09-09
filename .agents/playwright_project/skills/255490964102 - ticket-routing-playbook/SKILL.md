---
name: ticket-routing-playbook
description: How to pick the owning team and the priority for an inbound support ticket,
  including what to do when a ticket spans two teams. Use when triaging a ticket.
---

Use this skill whenever you are deciding which team owns an inbound support ticket, or what its priority should be.

## Teams

- `billing` — invoices, refunds, failed payments, plan changes, tax documents.
- `technical_support` — errors, outages, timeouts, rate limits, anything where the product is not doing what it says it does.
- `account_management` — ownership transfers, seat changes, SSO and workspace administration, renewals.
- `product_feedback` — feature requests and complaints about behaviour that is working as designed.

When a ticket touches two teams, route it to the one that can close it without a handoff. A failed payment caused by an expired card is `billing`, not `technical_support`, even though the customer describes it as an error.

## Priority

| Priority | Use when |
|---|---|
| `urgent` | The customer cannot work at all, data is at risk, or money is moving incorrectly right now. |
| `high` | A core workflow is broken for the customer but a workaround exists. |
| `medium` | Something is wrong and it is inconvenient, but the customer can proceed. |
| `low` | Questions, requests, and anything the customer is not blocked on. |

Plan tier never sets priority on its own. An enterprise customer asking a how-to question is `low`. A free-tier customer whose data is exposed is `urgent`.

## Summaries

Write the summary for the person picking up the ticket, not for the customer. One or two sentences, naming what broke and what the customer already tried.