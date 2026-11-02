"""A question: what a student asks once in a learning session, until its Ask answer is stored.

The package is being moved here from `routers/conversations.py`,
`attachment_repo` and `jobs/conversation_generation.py` in four steps (#204).
Step 1 (#217) moved only the rows the question keeps (`_store`); its entry
points arrive in step 2.
"""
