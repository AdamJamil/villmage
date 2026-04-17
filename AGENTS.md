This repository uses sapling. Do not use git commands. Use sl.

Style guide -- STRICTLY FOLLOW THESE AS BEST AS YOU CAN:
- Think extremely thoroughly through architecture before adding any code structure (files, classes, functions, etc.).
- Do not add files/classes/abstractions unless they clearly help.
- Prefer simple, minimal code.
- Remove bloat wherever you see it.
- Use strict type hinting through pyre. Pyre must pass in strict mode on your code. Do not use Any or similar hacks.
- Prefer small cohesive functions/files. Aim for no more than ~200 lines of actual logic in a file; more lines are fine if they are just data.
- Do not repeat code more than twice; create an abstraction and unify your logic.
- Write docstrings for all functions, classes, etc. Make them extremely clear and concise. Doing this right should account for a majority of your effort.
- Most importantly -- MAKE MULTIPLE PASSES OVER YOUR CODE TO IMPROVE IT. It is fine to spend the extra tokens.