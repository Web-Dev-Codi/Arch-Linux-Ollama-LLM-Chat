# Agent Continuation Prompt: Complete Refactoring Phases 2-4

## Mission
Complete the remaining 25% of the Arch-Linux-Ollama-LLM-Chat (OllamaTerm) refactoring project. The codebase is 75% complete with Phase 1 done and Phase 2-4 partially implemented. Your job is to integrate existing templates, refactor tools, and complete the architectural improvements.

## Current State
- **Branch:** `refactor` (10 commits ahead of origin, working tree clean)
- **Phase 1 (Critical Redundancies):** ✅ 100% complete (-1,476 LOC)
- **Phase 2 (God Class Refactoring):** 🟡 40% complete (2/5 managers integrated)
- **Phase 3 (Tool System Cleanup):** 🟡 20% complete (abstracts created, not applied)
- **Phase 4 (Architecture Improvements):** 🟡 30% complete (event bus/plugins created, not integrated)
- **Current app.py size:** 1,862 LOC
- **Target app.py size:** ~1,400-1,500 LOC

## Master Plan
**CRITICAL:** Follow `REFACTORING_IMPLEMENTATION_PLAN.md` (1,939 lines) for detailed step-by-step instructions. This document contains:
- Lines 877-1175: Phase 2 manager integration patterns
- Lines 1215-1415: Phase 3 tool refactoring patterns
- Lines 1444-1723: Phase 4 event bus and plugin integration

## Git Workflow (VERY IMPORTANT)

### Tagging Convention
Use semantic versioning with phase markers:
- **Phase milestones:** `v0.4.0-phase2`, `v0.4.0-phase3`, `v0.4.0-phase4`
- **Final release:** `v0.4.0` (when all phases complete)

### Git Operations for Each Completed Phase
```bash
# After completing a phase (e.g., Phase 2):
git add .
git commit -m "Complete Phase 2: God class refactoring - integrate remaining managers

- Integrate ConversationManager (replaces conversation persistence in app.py)
- Integrate CommandManager (replaces slash command handling in app.py)
- Integrate ThemeManager (replaces theme application in app.py)
- app.py reduced from 1,862 to ~1,400-1,500 LOC
- All managers use proper async/await patterns
- Lifecycle management wired into on_mount/on_unmount"

git tag -a v0.4.0-phase2 -m "Phase 2 complete: 5/5 managers integrated"

# After Phase 3:
git commit -m "Complete Phase 3: Tool system cleanup - apply abstract base classes"
git tag -a v0.4.0-phase3 -m "Phase 3 complete: 7 tools refactored, permission system consolidated"

# After Phase 4:
git commit -m "Complete Phase 4: Architecture improvements - integrate event bus and plugins"
git tag -a v0.4.0-phase4 -m "Phase 4 complete: Event-driven architecture operational"

# Final release (after testing):
git commit -m "Release v0.4.0: Complete refactoring - eliminate 2,313 LOC, reduce complexity"
git tag -a v0.4.0 -m "Major refactoring release: -2,313 LOC, god class eliminated, plugin architecture"
```

### Important Git Rules
1. **DO NOT PUSH** until all phases are complete and tested
2. **SAVE ALL COMMITS LOCALLY** - the user will review before pushing
3. **TAG EACH PHASE** after completion (phase2, phase3, phase4, then final v0.4.0)
4. **WORKING TREE MUST BE CLEAN** before moving to next phase
5. Verify clean state: `git status` should show "working tree clean"

---

## Phase 2: Complete Manager Integration (Week 1)

### Phase 2.3: Integrate ConversationManager (~200 LOC reduction)
**Status:** Template ready at `src/ollama_chat/managers/conversation.py` (110 LOC)

**Tasks:**
1. **Import and initialize** in `app.py`:
   ```python
   from .managers.conversation import ConversationManager
   
   def __init__(self):
       # ... existing code ...
       self.conversation_manager = ConversationManager(self.config_manager.conversations_dir)
   ```

2. **Replace conversation loading methods** (find these in app.py):
   - `_load_conversation_from_path()` → `self.conversation_manager.load_conversation(path)`
   - `_load_conversation_payload()` → Extract to manager
   - Auto-save logic in `_auto_save_on_exit()` → `self.conversation_manager.enable_auto_save()`

3. **Replace action methods**:
   - `action_save_conversation()` → Call `self.conversation_manager.save_conversation()`
   - `action_load_conversation()` → Call `self.conversation_manager.load_conversation()`
   - Update UI notifications to show manager results

4. **Wire lifecycle**:
   - In `on_mount()`: Call `self.conversation_manager.enable_auto_save()` if config says so
   - In `on_unmount()`: Auto-save is automatic (manager handles it)

**Expected outcome:** ~200 LOC removed from app.py

---

### Phase 2.4: Integrate CommandManager (~150 LOC reduction)
**Status:** Template ready at `src/ollama_chat/managers/command.py` (100 LOC)

**Tasks:**
1. **Import and initialize** in `app.py`:
   ```python
   from .managers.command import CommandManager
   
   def __init__(self):
       # ... existing code ...
       self.command_manager = CommandManager(self)
       self._register_all_commands()
   ```

2. **Register slash commands** in new `_register_all_commands()` method:
   ```python
   def _register_all_commands(self):
       self.command_manager.register_command("/clear", self.action_clear_chat, "Clear the chat history")
       self.command_manager.register_command("/new", self.action_new_conversation, "Start new conversation")
       self.command_manager.register_command("/save", self.action_save_conversation, "Save conversation")
       self.command_manager.register_command("/load", self.action_load_conversation, "Load conversation")
       self.command_manager.register_command("/image", self._handle_image_command, "Attach image")
       self.command_manager.register_command("/file", self._handle_file_command, "Attach file")
       self.command_manager.register_command("/export", self.action_export_chat, "Export chat")
       self.command_manager.register_command("/help", self._show_help, "Show commands")
   ```

3. **Replace command processing** in input handler:
   - Find where user input is processed (likely in `on_input_submitted()` or similar)
   - Before sending to LLM, check: `if input.startswith('/'): return self.command_manager.execute(input)`
   - Let manager handle command parsing and execution

4. **Add command completion** (optional):
   - Integrate with input widget for tab-completion
   - Use `self.command_manager.list_commands()` to show available commands

**Expected outcome:** ~150 LOC removed from app.py (slash command handling consolidated)

---

### Phase 2.5: Integrate ThemeManager (~100 LOC reduction)
**Status:** Template ready at `src/ollama_chat/managers/theme.py` (90 LOC)

**Tasks:**
1. **Import and initialize** in `app.py`:
   ```python
   from .managers.theme import ThemeManager
   
   def __init__(self):
       # ... existing code ...
       self.theme_manager = ThemeManager()
   ```

2. **Replace theme application methods**:
   - Find `_apply_theme()` method → Delete, replace with `self.theme_manager.apply_to_app(self, theme_name)`
   - Find `_style_bubble()` method → Delete, replace with `self.theme_manager.apply_to_bubble(bubble, role)`
   - Find `_restyle_rendered_bubbles()` → Delete, replace with manager method

3. **Update theme switching**:
   - In `action_change_theme()` or similar:
     ```python
     self.theme_manager.apply_to_app(self, new_theme)
     # Restyle all existing bubbles
     for bubble in self.query(MessageBubble):
         self.theme_manager.apply_to_bubble(bubble, bubble.role)
     ```

4. **Apply on widget creation**:
   - When creating new MessageBubble widgets:
     ```python
     bubble = MessageBubble(...)
     self.theme_manager.apply_to_bubble(bubble, role)
     ```

**Expected outcome:** ~100 LOC removed from app.py (theme logic centralized)

---

### Phase 2 Completion Checklist
- [ ] All 3 managers imported and initialized in app.py
- [ ] All manager methods replace app.py equivalents
- [ ] Lifecycle management wired (on_mount/on_unmount if needed)
- [ ] app.py reduced to ~1,400-1,500 LOC (verify with `wc -l src/ollama_chat/app.py`)
- [ ] Application runs without errors: `uv run ollama-chat`
- [ ] All manager features work (save/load conversations, slash commands, theme switching)
- [ ] Git commit and tag: `v0.4.0-phase2`

---

## Phase 3: Tool System Cleanup (Week 2)

### Phase 3.1: Apply Abstract Base Classes to Tools
**Status:** Abstract classes ready at `src/ollama_chat/tools/abstracts.py` (200 LOC)

**Pattern to follow for EACH tool:**
1. Change inheritance: `class XTool(Tool)` → `class XTool(FileOperationTool)` or `SearchTool`
2. Rename method: `async def execute(...)` → `async def perform_operation(...)` or `perform_search(...)`
3. Remove boilerplate:
   - Delete path resolution code (base class handles it)
   - Delete `check_file_safety()` calls (base class handles it)
   - Delete `notify_file_change()` calls (base class handles it)
4. Keep only core logic (the unique operation the tool performs)

**Tools to refactor (7 total):**

#### FileOperation Tools (4 tools):
- [ ] **ReadTool** (`tools/read_tool.py`, 164 LOC)
  - Inherit from `FileOperationTool`
  - Rename `execute()` → `perform_operation()`
  - Remove path resolution, keep file reading logic
  - Expected: ~30 LOC reduction

- [ ] **WriteTool** (`tools/write_tool.py`, 103 LOC)
  - Inherit from `FileOperationTool`
  - Rename `execute()` → `perform_operation()`
  - Remove safety checks and notifications, keep writing logic
  - Expected: ~25 LOC reduction

- [ ] **EditTool** (`tools/edit_tool.py`, 139 LOC)
  - Inherit from `FileOperationTool`
  - Rename `execute()` → `perform_operation()`
  - Remove boilerplate, keep edit logic
  - Expected: ~30 LOC reduction

- [ ] **ApplyPatchTool** (`tools/apply_patch_tool.py`, 274 LOC)
  - Inherit from `FileOperationTool`
  - Rename `execute()` → `perform_operation()`
  - Remove boilerplate, keep patch application logic
  - Expected: ~40 LOC reduction

#### Search Tools (3 tools):
- [ ] **GrepTool** (`tools/grep_tool.py`, 121 LOC)
  - Inherit from `SearchTool`
  - Rename `execute()` → `perform_search()`
  - Remove path resolution, keep grep logic
  - Expected: ~30 LOC reduction

- [ ] **GlobTool** (`tools/glob_tool.py`, 78 LOC)
  - Inherit from `SearchTool`
  - Rename `execute()` → `perform_search()`
  - Remove path resolution, keep globbing logic
  - Expected: ~20 LOC reduction

- [ ] **LsTool** (`tools/ls_tool.py`, 100 LOC)
  - Inherit from `SearchTool`
  - Rename `execute()` → `perform_search()`
  - Remove boilerplate, keep directory listing logic
  - Expected: ~25 LOC reduction

**Expected total reduction:** 200-250 LOC

---

### Phase 3.2: Consolidate Permission System
**Status:** Not started

**Tasks:**
1. **Add centralized permission checking** to `tools/base.py` (`ToolContext` class):
   ```python
   def check_permission(self, path: Path, operation: str) -> tuple[bool, str | None]:
       """Check if operation is allowed on path. Returns (allowed, error_message)."""
       # Check if path is outside project root
       # Check if path matches external_directory.py patterns
       # Return (True, None) if allowed, (False, "reason") if denied
   ```

2. **Update external_directory.py**:
   - Extract permission logic into standalone function
   - Make it usable by ToolContext.check_permission()

3. **Update all tools to use centralized checking**:
   - Replace duplicate permission code with `self.context.check_permission(path, "read")`
   - Remove redundant safety checks

**Expected reduction:** 80-100 LOC

---

### Phase 3 Completion Checklist
- [ ] All 7 tools refactored to use abstract base classes
- [ ] Permission system consolidated in ToolContext
- [ ] All tools tested: `uv run pytest tests/test_tools.py -v`
- [ ] Total reduction: ~260-390 LOC across tools
- [ ] Application runs with refactored tools: `uv run ollama-chat` and test /file, /image commands
- [ ] Git commit and tag: `v0.4.0-phase3`

---

## Phase 4: Architecture Improvements (Week 3)

### Phase 4.1: Integrate EventBus
**Status:** EventBus created at `src/ollama_chat/events/bus.py` (90 LOC), not integrated

**Tasks:**
1. **Create typed event classes** in `src/ollama_chat/events/domain.py`:
   ```python
   from dataclasses import dataclass
   from datetime import datetime
   
   @dataclass
   class FileEditedEvent:
       file_path: str
       operation: str  # "read", "write", "edit"
       timestamp: datetime
   
   @dataclass
   class ConnectionStateChangedEvent:
       is_connected: bool
       timestamp: datetime
   
   @dataclass
   class ConversationSavedEvent:
       conversation_id: str
       path: str
       timestamp: datetime
   
   @dataclass
   class CommandExecutedEvent:
       command: str
       success: bool
       timestamp: datetime
   
   # Add more events as needed
   ```

2. **Initialize EventBus** in `app.py`:
   ```python
   from .events.bus import EventBus
   
   def __init__(self):
       # ... existing code ...
       self.event_bus = EventBus()
       self._setup_event_subscribers()
   ```

3. **Set up subscribers** in `_setup_event_subscribers()`:
   ```python
   def _setup_event_subscribers(self):
       # Log file operations
       self.event_bus.subscribe("file.edited", self._on_file_edited)
       
       # Update UI on connection changes
       self.event_bus.subscribe("connection.state_changed", self._on_connection_changed)
       
       # Track conversation saves
       self.event_bus.subscribe("conversation.saved", self._on_conversation_saved)
   ```

4. **Publish events** throughout the codebase:
   - In tools: `self.context.app.event_bus.publish(FileEditedEvent(...))`
   - In managers: `self.app.event_bus.publish(ConversationSavedEvent(...))`
   - In connection monitoring: `self.event_bus.publish(ConnectionStateChangedEvent(...))`

5. **Replace existing observer patterns** with event bus:
   - ConnectionManager callback → Event
   - Tool notifications → Events
   - Manager callbacks → Events

**Expected outcome:** Event-driven communication between components

---

### Phase 4.2: Integrate Plugin System
**Status:** Plugin system created at `src/ollama_chat/plugins/interface.py` (170 LOC), not integrated

**Tasks:**
1. **Create plugins directory** in project root:
   ```bash
   mkdir -p plugins/examples
   ```

2. **Initialize plugin manager** in `app.py`:
   ```python
   from .plugins.interface import PluginManager
   
   def __init__(self):
       # ... existing code ...
       self.plugin_manager = PluginManager(self)
   
   async def on_mount(self):
       # ... existing code ...
       await self.plugin_manager.load_plugins("./plugins")
       await self.plugin_manager.enable_all()
   
   async def on_unmount(self):
       await self.plugin_manager.disable_all()
       # ... existing code ...
   ```

3. **Create example plugin** in `plugins/examples/sample_plugin.py`:
   ```python
   from ollama_chat.plugins.interface import Plugin
   
   class SamplePlugin(Plugin):
       def get_name(self) -> str:
           return "sample"
       
       def get_version(self) -> str:
           return "1.0.0"
       
       async def on_enable(self):
           self.app.notify("Sample plugin enabled!")
       
       async def on_disable(self):
           self.app.notify("Sample plugin disabled!")
       
       def get_tools(self):
           return []  # Can return custom tools
       
       def get_commands(self):
           return {}  # Can return custom slash commands
   ```

4. **Wire plugin tools** into tool system:
   - After loading plugins, register their tools: `self.plugin_manager.get_all_tools()`
   - Add plugin commands to CommandManager: `self.plugin_manager.get_all_commands()`

**Expected outcome:** Plugin system operational, can load external plugins at startup

---

### Phase 4.3: Dependency Injection (Optional)
**Status:** Not started (this is optional, can be skipped if time is limited)

**Tasks (if implemented):**
1. Create `src/ollama_chat/container.py` with DI container
2. Register all managers, services, and dependencies
3. Refactor app.py initialization to use container
4. Improve testability by injecting mocks

**Note:** This can be deferred to v0.5.0 if time is constrained

---

### Phase 4 Completion Checklist
- [ ] EventBus integrated and operational
- [ ] Typed event classes created in events/domain.py
- [ ] All major components publish and subscribe to events
- [ ] Plugin system integrated
- [ ] Plugin manager loads plugins at startup
- [ ] Example plugin works
- [ ] Application runs with event bus and plugins: `uv run ollama-chat`
- [ ] Git commit and tag: `v0.4.0-phase4`

---

## Final Testing & Release (Week 4)

### Comprehensive Testing
**Note:** User deferred testing until all phases complete. Now is the time.

1. **Run existing test suite:**
   ```bash
   uv run pytest tests/ -v
   ```

2. **Manual testing checklist:**
   - [ ] Start application: `uv run ollama-chat`
   - [ ] Send a message to Ollama
   - [ ] Test slash commands: `/clear`, `/new`, `/save`, `/load`, `/help`
   - [ ] Change theme
   - [ ] Attach file with `/file`
   - [ ] Attach image with `/image`
   - [ ] Save and load conversation
   - [ ] Test connection monitoring (disconnect Ollama, reconnect)
   - [ ] Check auto-save on exit

3. **Verify metrics:**
   ```bash
   # Check final app.py size
   wc -l src/ollama_chat/app.py
   # Should be ~1,400-1,500 LOC (down from 1,949)
   
   # Check total LOC reduction
   git diff v0.4.0-phase1..HEAD --stat
   # Should show ~2,300+ LOC eliminated
   
   # Check code duplication
   # Should be <2%
   ```

4. **Update documentation:**
   - [ ] Update `REFACTORING_PROGRESS.md` with final status (all phases 100%)
   - [ ] Update `FINAL_STATUS.md` with completion date and final metrics
   - [ ] Update `README.md` if needed (new plugin system, architecture changes)

---

### Final Release

1. **Create final commit:**
   ```bash
   git add .
   git commit -m "Release v0.4.0: Complete refactoring - eliminate 2,313 LOC

   Complete 4-phase refactoring of Arch-Linux-Ollama-LLM-Chat:
   
   Phase 1 (Critical Redundancies): -1,476 LOC
   - Removed custom_tools.py duplicate system
   - Extracted common utilities
   - Consolidated truncation logic
   
   Phase 2 (God Class Refactoring): -450 LOC from app.py
   - Integrated 5 managers: Connection, Capability, Conversation, Command, Theme
   - app.py reduced from 1,949 to ~1,400-1,500 LOC
   - Improved separation of concerns
   
   Phase 3 (Tool System Cleanup): -260 LOC
   - Refactored 7 tools to use abstract base classes
   - Consolidated permission system
   - Eliminated duplicate code
   
   Phase 4 (Architecture Improvements): Event-driven + Plugins
   - Integrated EventBus for component communication
   - Integrated plugin system for extensibility
   - Typed event classes for type safety
   
   Total impact:
   - 2,313 LOC eliminated
   - Code duplication: <2%
   - Complexity significantly reduced
   - Plugin architecture for future extensions"
   ```

2. **Create final tag:**
   ```bash
   git tag -a v0.4.0 -m "Major refactoring release

   - Eliminated 2,313 LOC through strategic refactoring
   - Broke up god class (app.py) into 5 specialized managers
   - Implemented abstract tool base classes
   - Added event-driven architecture
   - Introduced plugin system for extensibility
   - Reduced code duplication to <2%
   - Improved testability and maintainability"
   ```

3. **Verify tags:**
   ```bash
   git tag
   # Should show:
   # v0.4.0-phase1
   # v0.4.0-phase2
   # v0.4.0-phase3
   # v0.4.0-phase4
   # v0.4.0-refactoring-complete (old tag)
   # v0.4.0
   ```

4. **Final status check:**
   ```bash
   git status
   # Should show: "working tree clean"
   
   git log --oneline --graph --all
   # Should show all commits and tags
   ```

5. **DO NOT PUSH** - let user review:
   ```bash
   # User will review and then push:
   # git push origin refactor
   # git push origin --tags
   ```

---

## Success Criteria

### Code Metrics
- ✅ app.py reduced from 1,949 to ~1,400-1,500 LOC (25-28% reduction)
- ✅ Total LOC eliminated: 2,300+ across entire codebase
- ✅ Code duplication: <2%
- ✅ All managers integrated and functional
- ✅ All tools refactored to use abstract bases
- ✅ Event bus and plugin system operational

### Functional Requirements
- ✅ Application starts without errors
- ✅ All existing features work (chat, tools, themes, save/load)
- ✅ Slash commands work through CommandManager
- ✅ Themes applied through ThemeManager
- ✅ Conversations saved/loaded through ConversationManager
- ✅ Events published and handled correctly
- ✅ Plugins load and can be enabled/disabled

### Git Requirements
- ✅ All phases tagged: v0.4.0-phase2, v0.4.0-phase3, v0.4.0-phase4
- ✅ Final release tagged: v0.4.0
- ✅ Working tree clean
- ✅ All commits on `refactor` branch
- ✅ Ready for user review (not pushed)

### Documentation Requirements
- ✅ REFACTORING_PROGRESS.md updated with 100% completion
- ✅ FINAL_STATUS.md updated with completion date and metrics
- ✅ README.md updated if necessary
- ✅ All code properly documented

---

## Important Constraints & Reminders

1. **Follow the master plan:** `REFACTORING_IMPLEMENTATION_PLAN.md` is your bible
2. **Test incrementally:** Test after each phase, not at the end
3. **Keep working tree clean:** Commit after each phase completion
4. **Tag each milestone:** Don't forget phase tags!
5. **Do not push:** User will review and push manually
6. **Preserve functionality:** Don't break existing features
7. **Maintain async patterns:** All managers use proper async/await
8. **Type safety:** Use type hints everywhere
9. **Error handling:** Maintain existing error handling patterns
10. **User experience:** Don't change UI/UX without necessity

---

## Emergency Contacts & Resources

- **Master Plan:** `REFACTORING_IMPLEMENTATION_PLAN.md` (lines 877-1723)
- **Original Analysis:** `CRITICAL_ANALYSIS.md`
- **Progress Tracking:** `REFACTORING_PROGRESS.md`
- **Current Status:** `FINAL_STATUS.md` (lines 1-471)
- **Manager Templates:** `src/ollama_chat/managers/` (all ready to integrate)
- **Abstract Tools:** `src/ollama_chat/tools/abstracts.py` (full documentation)
- **Event Bus:** `src/ollama_chat/events/bus.py` (implementation complete)
- **Plugin System:** `src/ollama_chat/plugins/interface.py` (implementation complete)

---

## Execution Order (tl;dr)

```
Week 1: Phase 2 (Manager Integration)
├── Day 1-2: ConversationManager → app.py
├── Day 3-4: CommandManager → app.py
├── Day 5: ThemeManager → app.py
└── Commit & Tag: v0.4.0-phase2

Week 2: Phase 3 (Tool Refactoring)
├── Day 1-2: Refactor 4 FileOperation tools
├── Day 3: Refactor 3 Search tools
├── Day 4-5: Consolidate permission system
└── Commit & Tag: v0.4.0-phase3

Week 3: Phase 4 (Architecture)
├── Day 1-2: EventBus integration + typed events
├── Day 3-4: Plugin system integration
├── Day 5: DI container (optional)
└── Commit & Tag: v0.4.0-phase4

Week 4: Testing & Release
├── Day 1-2: Comprehensive testing
├── Day 3: Documentation updates
├── Day 4-5: Final verification
└── Commit & Tag: v0.4.0
```

Good luck! The codebase is in excellent shape and all templates are ready. You're just wiring things together. 🚀
