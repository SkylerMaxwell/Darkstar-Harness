# Notebook tabs

A **Notebook** tab is a notebook you write in plain words. Right-click **+** and choose **Notebook** from the menu: the tab opens with an empty notebook, and you write the first step in its first cell.

## Cells

- **Instruction cells** hold what a step should do, in your words. When you run one, Darkstar's agent writes its Python, runs it and fixes what fails. Click **Python** under the instruction to see the code; **Edit code** lets you change it by hand, and **Rewrite** has the agent write it again from your instruction.
- **Code cells** hold Python you write yourself. The agent reads them but never changes them. **Ctrl+M** switches a cell between Instruction and Code.
- **Markdown cells** hold notes. Click a note to edit it.
- Hover between two cells to add an Instruction, Code or Markdown cell there. Hover a cell for its run, move and delete buttons. There is always an empty cell at the bottom to type the next step.

## Running

- **Ctrl+Enter** runs the cell you are in, **Shift+Enter** runs it and moves to the next one, and **Run All** runs every cell from the top.
- The agent reads the whole notebook above the cell. When your new instruction changes what earlier cells should do, it changes their code too, so the notebook stays one clean program; a cell it changed shows **Revised by the agent**. If you edit an instruction, its cell shows **Instruction changed** and is rewritten at the next run.
- A cell that already has code for its instruction just runs. Running a cell first runs, in order, any earlier cell that changed or has not run since the kernel started.
- **Stop** (beside a running cell) stops the agent and interrupts the code. A cell that will not stop is ended by restarting the kernel, which clears its variables.

## The kernel

- All cells share one Python kernel: Darkstar's own Python environment, started in the tab's working folder with your Windows rights, like an Agent chat's tools. Only run notebooks you trust with your computer.
- A cell shows what it printed, the value of its last line (tables for pandas data, with a bar chart for a short list of numbers, figures and images), a progress bar with time left for loops written with `progress(...)`, and below it the run time and the variables it made.
- A line like `%pip install pandas` installs a package into the kernel's environment, and a line starting with `!` runs a command. Cells cannot ask for typed input.
- **Restart** starts a fresh kernel, **Clear Outputs** clears every result, and **Variables** lists what the kernel holds.
- The cells and their last results are saved with the tab. The kernel itself does not survive closing the tab or Darkstar: run the cells again to rebuild its variables.

## Good to know

- The notebook uses the model chosen in Settings, like a chat. A model without tool calling cannot write cells.
- The agent only changes Instruction cells at or above the one you run, never Code or Markdown cells.
- Skills, MCP servers and Global Memory are not used in notebooks.
