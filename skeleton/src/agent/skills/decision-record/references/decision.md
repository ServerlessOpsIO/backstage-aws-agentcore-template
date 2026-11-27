# Stage: decision

**Aim**: the participants choose, give their reason, and say what they will do next.

## What to establish

1. Ask which option the participants choose. DO NOT say which is best, even when asked.
   Asked for a view, set out the tradeoff between the options as recorded and ask which
   goal matters most.
2. Ask for the reason in their words.
3. Ask what has to happen because of the decision, and who is responsible for each thing.

## Recording

- Use the `add_outcome` tool for the decision, with the option's identifier, the reason
  and `decided_by`: whoever said it and everyone who agreed. Only people in the session
  can be named.
- When the participants change their minds, change it with `update_outcome`. A session
  records one decision; a second one replaces the first.
- Use the `add_action` tool for each thing to be done. When nobody is named as responsible,
  ask once. If none is named, leave the owner empty.
- When the participants cannot agree, DO NOT settle it. Record what is unresolved with
  `add_open_question`.

## Before closing the stage

- When the reason contradicts something in the context, ask about it once. If the
  participants keep their reason, call `add_note` with kind `questioned_kept`.
- Then call `complete_stage`.
