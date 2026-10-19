---
name: escalation-and-reply-tone
description: When a ticket must go to a human before any reply is sent, and how the
  first reply should read. Use when drafting a customer reply or setting needs_human_review.
---

Use this skill when drafting the first reply to a customer, or when deciding whether a ticket needs a human before anything is sent.

## Always escalate to a human

Set `needs_human_review` to true, and do not send an automated reply, when the ticket involves any of:

- Security: suspicious logins, credential exposure, anything the customer describes as a breach.
- Data exposure: one customer seeing another customer's data, in any amount.
- Billing disputes: a charge the customer says they did not authorise, or a refund they have already been refused once.
- Legal risk: threats of legal action, regulatory requests, deletion requests citing a specific law.

Urgency alone is not escalation. A production outage with a known cause and a workaround is `urgent` and still does not need human review.

## Tone

Open with what you understood, in the customer's own terms, before saying what you will do. Never open with an apology template.

Say what happens next and who does it. "I have routed this to our billing team, who will reply today" beats "your ticket has been escalated".

Do not promise a timeline the team has not committed to. If you do not know when something will be fixed, say what you will tell them and when.

Match the customer's register. A one-line question gets a one-line answer; a detailed report gets a reply that addresses each part in the order they raised it.