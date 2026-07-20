import os
import re
from collections import Counter


class ErrorLogService:
    @staticmethod
    def get_parsed_errors(page=1, per_page=50, search="", level_filter="", error_file="logs/errors.log"):
        parsed_errors = []

        if os.path.exists(error_file):
            with open(error_file, "r", encoding="utf-8") as f:
                raw = f.read()

            entries = re.split(r"\n(?:\s*\n)+", raw)
            for entry in reversed(entries):
                entry = entry.strip()
                if not entry:
                    continue
                lines = entry.splitlines()

                header_match = re.match(
                    r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s+(\w+)\s+in\s+([^:]+):(\d+)$",
                    lines[0].strip(),
                )
                if not header_match:
                    parsed_errors.append(
                        {
                            "timestamp": "",
                            "level": "UNKNOWN",
                            "module": "",
                            "lineno": "",
                            "message": lines[0] if lines else "",
                            "path": "",
                            "traceback": "\n".join(lines[1:]),
                            "raw": entry,
                        }
                    )
                    continue

                ts, level, mod, ln = header_match.groups()
                message = ""
                path = ""

                i = 1
                if i < len(lines) and lines[i].strip().startswith("Message:"):
                    message = lines[i].strip()[len("Message:") :].strip()
                    i += 1
                if i < len(lines) and lines[i].strip().startswith("Path:"):
                    path = lines[i].strip()[len("Path:") :].strip()
                    i += 1

                tb_text = "\n".join(lines[i:]).strip()
                if tb_text == "None":
                    tb_text = ""

                parsed_errors.append(
                    {
                        "timestamp": ts,
                        "level": level,
                        "module": mod,
                        "lineno": ln,
                        "message": message,
                        "path": path,
                        "traceback": tb_text,
                        "raw": entry,
                        "hash": hash(entry) & 0xFFFFFFFF,
                    }
                )

        # Filtering
        if search:
            search = search.strip().lower()
            parsed_errors = [
                e
                for e in parsed_errors
                if search in e["message"].lower()
                or search in e["module"].lower()
                or search in e["traceback"].lower()
                or search in e["path"].lower()
            ]
        if level_filter:
            level_filter = level_filter.upper()
            parsed_errors = [e for e in parsed_errors if e["level"] == level_filter]

        total = len(parsed_errors)
        start = (page - 1) * per_page
        end = start + per_page
        paginated = parsed_errors[start:end]
        total_pages = max(1, (total + per_page - 1) // per_page)

        # Stats
        stats = {}
        if parsed_errors:
            stats["by_level"] = dict(Counter(e["level"] for e in parsed_errors))
            stats["by_module"] = dict(Counter(e["module"] for e in parsed_errors if e["module"]).most_common(10))
            stats["total"] = total

        return paginated, total_pages, total, stats
