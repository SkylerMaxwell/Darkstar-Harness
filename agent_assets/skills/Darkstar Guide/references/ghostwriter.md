# Ghostwriter tabs

A **Ghostwriter** tab is a manuscript you write together with a model: you write, and the model continues the text from where it ends. It is made for research writing (papers and preprints, thesis chapters, literature reviews, proposals, reports) and works for any other prose. It uses whichever local GGUF model is loaded, with the sampling settings of Text Generation.

## Starting one

Right-click **+** and choose **Ghostwriter** from the menu: the tab opens with an empty manuscript. The tab has no message box: you write directly in the page, and the model continues from where your text ends. The tab is named from the manuscript's opening when conversation naming is on.

## Writing and generating

- **Generate**, the **>** at the bottom right of the page (or **Ctrl+Enter**) asks the model to continue the manuscript from its end. Its words stream into the page; **Stop** (the > becomes a stop square while the model writes, or **Esc**) ends it and keeps what it wrote. If a generation fails, the reason appears beside the >. While it writes, the page cannot be edited.
- Text the model wrote is shown in a softer shade than your own; the newest passage flashes once. Any edit you make inside the model's text becomes your text.
- **Retry** (or **Ctrl+Shift+Enter**) writes the last passage again. Every version is kept as a take: the arrows beside Retry, or **Alt+Left** and **Alt+Right**, switch between them. Editing the passage ends its takes.
- **Undo** and **Redo** (**Ctrl+Z**, **Ctrl+Y** or **Ctrl+Shift+Z**) step through your edits and the model's passages. This history lasts while Darkstar runs.
- The word count is at the right of the toolbar. **Export** saves the manuscript as plain text (.txt) or Markdown (.md, with the title as its heading) wherever you choose.
- Paste always arrives as plain text. Clicking the page below or beside the text puts the cursor at its end.
- The page, its type and the Brief scale with the window and the screen. A Ghostwriter tab is a single page, so it has no spaces (no icons in the status bar) and no Action Engine.

## The Brief

**Brief** in the toolbar shows or hides the panel beside the page. What it holds is given to the model with every generation:

- **Memory**: what the model should always keep in mind, such as the research question, the field, the method, terminology and style.
- **Author's Note**: where the next passages should go or how they should read, for example "Next, compare against the baselines in Table 2."
- **Length**: Short (the default), Medium or Long passages per generation. Short stops at the end of its first sentence.
- **References**: papers, findings, datasets and definitions. Each has a title, keys (an author, an acronym, a term, separated by commas) and notes. A reference enters the model's view when one of its keys appears in the recent text (case does not matter), or always when **Always** is on; its switch turns it off without deleting it. The references the last generation used have a lit dot.

The model is told to cite only works that are in the References or already in the manuscript, never to invent references, data or results, and to write a visible placeholder such as [citation needed] or [value] where it lacks one. Always check what it writes against your sources.

## Context

Darkstar decides how much of the manuscript fits the model's context. When the manuscript is longer, the model sees its most recent part, beginning at a paragraph. The model is asked for the next passage, with reasoning turned off, and it has no tools; Darkstar joins the passage to your text exactly where it stops, even in the middle of a word. **P** shows the exact request it received. If Memory and the References are too long to leave room for the manuscript, generating stops with a message saying so: shorten them or load the model with a larger context.

## What is saved

The manuscript (with who wrote what), Memory, the Author's Note, Length, the References and whether the Brief is open are saved with the tab. The undo history and the takes are not.
