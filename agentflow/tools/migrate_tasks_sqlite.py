import re
from pathlib import Path
import json

def migrate():
    project_root = Path(__file__).resolve().parents[2]
    ep_path = project_root / "execution_plan.md"
    archive_path = project_root / ".agentflow" / "addendums_archive.md"
    tasks_path = project_root / "tasks.json"

    # Find complete tasks
    complete_task_ids = set()
    if tasks_path.exists():
        try:
            tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
            for task in tasks_data.get("tasks", []):
                if task.get("status") == "complete":
                    complete_task_ids.add(task.get("task_id"))
        except Exception:
            pass

    if not complete_task_ids:
        print("No complete tasks found.")
        return

    ep_content = ep_path.read_text(encoding="utf-8")
    
    # We will find sections starting with `## Addendum: T-NNN` and ending before the next `## ` or EOF
    new_archive_content = ""
    if archive_path.exists():
        new_archive_content = archive_path.read_text(encoding="utf-8")

    ep_lines = ep_content.splitlines(keepends=True)
    new_ep_lines = []
    
    current_addendum_lines = []
    current_task_id = None
    in_addendum = False
    
    for line in ep_lines:
        match = re.match(r"^## Addendum: (T-\d+)", line)
        if match:
            # If we were already in an addendum, we need to decide what to do with it
            if in_addendum:
                if current_task_id in complete_task_ids:
                    addendum_str = "".join(current_addendum_lines)
                    if addendum_str not in new_archive_content:
                        if new_archive_content and not new_archive_content.endswith("\n\n"):
                            new_archive_content += "\n\n"
                        new_archive_content += addendum_str
                else:
                    new_ep_lines.extend(current_addendum_lines)
            
            current_task_id = match.group(1)
            in_addendum = True
            current_addendum_lines = [line]
            continue
            
        if in_addendum:
            if line.startswith("## "):
                # Addendum ended
                in_addendum = False
                if current_task_id in complete_task_ids:
                    addendum_str = "".join(current_addendum_lines)
                    if addendum_str not in new_archive_content:
                        if new_archive_content and not new_archive_content.endswith("\n\n"):
                            new_archive_content += "\n\n"
                        new_archive_content += addendum_str
                else:
                    new_ep_lines.extend(current_addendum_lines)
                new_ep_lines.append(line)
            else:
                current_addendum_lines.append(line)
            continue
            
        new_ep_lines.append(line)

    if in_addendum:
        if current_task_id in complete_task_ids:
            addendum_str = "".join(current_addendum_lines)
            if addendum_str not in new_archive_content:
                if new_archive_content and not new_archive_content.endswith("\n\n"):
                    new_archive_content += "\n\n"
                new_archive_content += addendum_str
        else:
            new_ep_lines.extend(current_addendum_lines)

    # Write back
    ep_path.write_text("".join(new_ep_lines), encoding="utf-8")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(new_archive_content, encoding="utf-8")
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
