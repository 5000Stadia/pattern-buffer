# Brief: write an original novella, plus its hidden answer key

You are writing a brand-new work of fiction. It will be used to test a system that reads a book and
builds a model of its world (who is who, where things are, who knows what, and how all of that
changes over time). The test only works if the book is genuinely new: no reader, human or machine,
can have seen it before.

## The book

- **Be original and go somewhere strange.** Don't write a retelling, pastiche or homage, and avoid
  familiar settings (no Victorian London, no generic fantasy kingdom, no detective agency or
  spaceship crew). Invent the world, its customs, its names and its kinds of objects. Make it vivid
  and odd, and still readable as a story.
- **Length:** about 25,000 words in 12 chapters of roughly 2,000 words each. Write prose, not an
  outline.
- **Cast:** 8 to 14 named characters, 6 to 12 named places (some rooms or containers inside
  others), and 10 to 20 objects that matter, some of which change hands or places.
- **Make the world hard to track, fairly.** A careful human reader must be able to follow every
  point below from the text alone.
  - Characters are referred to in several ways: full name, first name, a title or role, a
    nickname, and sometimes only by description ("the woman with the copper hand").
  - At least two different characters have confusingly similar names or the same title.
  - At least one character turns out to be the same person as someone met earlier under another
    name. The text must make this clear at some point.
  - Objects move: they are carried, hidden inside containers, given, stolen, swapped or destroyed.
    At least three objects are in containers whose contents are revealed only later.
  - Knowledge differs: some characters learn things others never do, and at least one character
    believes something false for most of the book.
  - At least one fact is stated early and later corrected (a lie, or a mistake).
- **No real people, brands or existing fictional characters.** Don't reuse distinctive names from
  well-known works.

## The answer key (the reader of the book never sees this)

Write `key.json` with these fields:

```json
{
  "title": "...",
  "chapters": [{"n": 1, "file": "ch01.md", "words": 0}],
  "entities": {
    "<short_key>": {"kind": "person|place|object|group",
                    "aliases": ["every way the text refers to it, lowercase, exactly as written"],
                    "first_chapter": 1}
  },
  "same_as": [["<key>", "an alias used before the reveal", "chapter of the reveal"]],
  "not_same": [["<key_a>", "<key_b>", "why a reader might confuse them"]],
  "locations": [{"entity": "<key>", "in": "<key>", "from_chapter": 1, "to_chapter": 3,
                 "evidence": "short quote"}],
  "holdings": [{"entity": "<object key>", "held_by": "<person key>", "from_chapter": 1,
                "to_chapter": 2, "evidence": "short quote"}],
  "containers": [{"container": "<key>", "contents": ["<key>"], "revealed_chapter": 5,
                  "evidence": "short quote"}],
  "knowledge": [{"who": "<person key>", "learns": "a plain statement", "chapter": 4,
                 "evidence": "short quote"}],
  "false_beliefs": [{"who": "<person key>", "believes": "...", "from_chapter": 2,
                     "corrected_chapter": 10}],
  "corrections": [{"claim": "...", "stated_chapter": 2, "corrected_chapter": 8,
                   "evidence": "short quote"}]
}
```

- Every alias must appear in the text, letter for letter, ignoring case.
- Every `evidence` quote must be copied exactly from the chapter it names.
- `to_chapter` may be null when the fact holds to the end.
- The key must be complete for everything the bullets above ask for, and accurate. If the story
  changes while you write, update the key.

## Files to write, in the current directory

- `ch01.md` to `ch12.md`: each starts with `# Chapter N: <title>` and then the prose.
- `key.json`: the answer key.
- `NOTES.md`: a few lines on the premise, and a confirmation that the work is original.

Before you finish, check the key against the text: every alias and every quote must be present
where the key says it is. Fix any mismatch.
