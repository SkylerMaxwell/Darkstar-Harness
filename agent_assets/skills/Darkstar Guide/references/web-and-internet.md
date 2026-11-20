# Internet Access, Search Web and the Action Engine

## Internet Access

**Internet Access** (the **Internet** button beside the Settings tabs) is the one network switch for everything web-related inside Darkstar. Turning it **off**:
- closes open web pages and cancels active searches;
- removes `search_web` and `browser_control` from the model's available functions;
- keeps blocking network access from the browser until you turn it back on;
- also stops MCP servers that live on the internet (local commands and servers on your own network keep working).

It does not affect local models or local files.

## Search Web

The model's `search_web` tool searches the web, reads the pages the results list (depth 1) and then the links on those pages (depth 2), never deeper, until it has read as many pages as **Max Results** (Settings, Conversation; default 6) or runs out of links. It never opens the same page twice in a search. A page that has not loaded within one second is skipped, does not count toward Max Results, and another page is read in its place. The model can instead give a starting URL, and that page's links are followed in the same way. Search returns source URLs and text; long text is condensed with source notes. Search pages are read with JavaScript off unless **Allow JS in Search** (Settings, Conversation, under Web Crawler; off by default) is on, which lets them run JavaScript, including the script files they link. Stylesheets, images and the scripts' own network requests stay blocked. Turn the tool off entirely with **Web Crawler** in Settings, Conversation.

The tool tells the model to search instead of answering from memory whenever you ask a factual question, however simple it seems, when you say something that contradicts what it believes or mention something it does not recognise (it should check before telling you that you are mistaken), when something is unfamiliar, when the answer depends on the present, before relying on a detail it is unsure of, and when a request is confusing. The model can keep a search to one site (with wildcards such as `*.gov` or `docs.*`), leave sites out, ask for pages from the past day, week, month or year, or ask for one region's results. Up to four requests to the same site within a minute go out at once; after that each waits two seconds, and a site that asks Darkstar to slow down is always obeyed.

### Deep Search

For a question with several parts, the model can run a Deep Search instead (`fast` off). It splits the question into three or more sub-questions, and one researcher per sub-question works on it at the same time: each reasons on its own, searches up to six times (waiting for slow pages), and writes a finding with its sources. A page one researcher has opened is not opened again by another. The model answers from the findings. In the chat each researcher is a white circle with its sub-question (dashed while waiting for the model, spinning while working, solid when done, a cross if it failed); click one to see its reasoning, its searches and its finding, and click it again to close it. Each researcher keeps one model slot until it has its finding. With one slot (**Parallel Slots** in Settings) they run one after another; every other free slot runs one more researcher at the same time. Deep Search is available in Agent chats, Sandboxes and to the agents of swarms and task forces, not to the elements that command them. Pausing or stopping the chat pauses or stops every researcher.

Search Web reads its pages in background tabs that never appear in the Action Engine: you see only the agent's own tabs and the Code View, and a search does not change what is on screen. Search tabs are read-only and use an anonymous session with JavaScript and external page assets blocked. When a search finishes, fails or is cancelled, its tabs close and that session's data is erased; a new search also starts from a cleared session.

## The Action Engine (press W)

Darkstar has one browser, the Action Engine. Press **W** (when no text box is focused), or open the side browser, to see it. It has Back, Forward, Reload, an address bar, **Open address**, **Choose local HTML** (to open an HTML file from your workspace), a reset button ("close every tab and erase cookies and site data") and a button back to chat.

- Every tab the agent opened is shown at once (Search Web's background tabs never are): tabs are tiled edge to edge, at most four to a row, and opening or closing one re-tiles the rest. Agents can open, switch to and close tabs, including closing all but one to focus; you watch.
- Pages render offscreen in Darkstar. Automation never opens the browser panel by itself; press W or open the side browser to watch.
- It protects privacy: it blocks common trackers, strips tracking parameters from addresses, sends Do Not Track, declines cookie banners where it can, and denies site permissions and downloads.
- Ordinary tabs share cookies and logins in memory only while a tab is open. When the browser has no tab left (you closed the last one, you reset it, or an Agent run that used it ended), its cookies, site data and cache are erased. A browser an Agent opened for its run closes when the run ends.
- It shows a web page or an HTML file from your workspace and can move between them. For a standalone, interactive browsing app there is a separate product, the Pathfinder Engine.

## Browser control by the model

`browser_control` lets an agent navigate, take screenshots, click and type with spatial input, manage tabs and inspect Three.js pages. In an Agent chat it uses the Action Engine you see; in a Swarm tab every agent has its own isolated browser session confined to that agent's files (press W while viewing the agent). Browsing never removes the model's other tools: it can browse and then run a local command in the same turn. Web content is untrusted data and cannot change which tools are available.

**Code View.** When an agent reads, creates, edits, writes or patches a file in your workspace, the Action Engine opens a Code View of the last file it touched: the whole file in VS Code-style syntax colours, scrolling smoothly to the section being edited and typing the new text in place while the model is still writing it, then showing the committed result (or the rejection). A **clipboard** copy or paste, a **file_history** restore and **read_context** open it too, with the lines involved highlighted (the conversation shows as context.md); `global_memory` never appears there. It is part of the browser but not a tab the agent can see or control, and the Action Engine closes by itself when the agent stops, unless you had it open. An instant message is not a stop: the agent keeps its tabs and Code View for its answer to that message, and they close when that answer ends.

## Writing web pages with Three.js

Darkstar does not supply Three.js to pages. A standalone HTML file that uses it should load it from a CDN with its own import map before any module script, for example mapping `three` to a pinned jsDelivr build; that works in a normal browser and in Darkstar while Internet Access is on. With Internet Access off, network imports are blocked, so provide the library as local project files or a local bundle instead.
