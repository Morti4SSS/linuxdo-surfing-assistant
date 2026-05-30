# Continuous Loop

Use this reference when the user invokes `/goal`, asks Codex to keep surfing, or wants open-ended Linux.do goldmining.

## Loop

1. Load or create a frontier queue with the state helper.
2. Select the next batch across `new`, `active-old`, and `low-traffic`.
3. Use Codex 内置浏览器 to read each post deeply.
4. Record readings with the reading schema.
5. Extract discovery leads:
   - author-tracking: high-signal authors;
   - comment-reference: Linux.do links and referenced discussions;
   - tool-lookup: tools, skills, plugins, MCP servers, CLI names, workflows;
   - skill-workflow-evidence: community evidence for skill management.
6. Save a session. This merges discovery queues back into the frontier.
7. Continue if the goal is not met and the budget allows it.

## Extension Rule

持续迭代 means each batch can reshape the next batch. If a post mentions another Linux.do thread, a tool, an author, a risk, or a comparison that is relevant to the user's target, add it as a lead. Then 延展冲浪 from that lead rather than staying on the original list.

Do not extend every link. Extend only when it can improve the target:

- better evidence for a tool or skill;
- strong positive or negative community feedback;
- a workflow that solves the user's current bottleneck;
- a reply that names a better alternative;
- an author who repeatedly produces high-signal AI workflow content.

## Stop Conditions

Stop when one of these is true:

- user target is satisfied;
- next batch is empty;
- read budget or wall-clock budget is reached;
- several consecutive batches produce no high-value leads;
- all remaining candidates are duplicates, low confidence, or off target.

When stopping, explain the stop reason and what remains in the frontier. Do not present a stop as final truth; present it as the end of the current surf pass.

## Browser Discipline

Linux.do reading depends on saved login state. If Codex 内置浏览器 is not logged in, ask the user to log in. Do not scrape protected content with unauthenticated HTTP. Do not use computer-use for ordinary post reading.

For active-old posts, read historical context. For low-traffic posts, spend limited budget and mark whether the post is worth deeper follow-up.
