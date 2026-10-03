// ---------------------------------------------------------------------------
// Unified-diff parser. Hunk bodies are read by the counts in their @@ header,
// not by guessing from prefixes, so a removed line that starts with "--" is
// never mistaken for a file header. Never throws: malformed input returns
// whatever parsed cleanly up to that point.
// ---------------------------------------------------------------------------

export interface DiffLine {
  kind: "context" | "add" | "del";
  text: string;
  oldLine: number | null;
  newLine: number | null;
}

export interface DiffHunk {
  header: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: DiffLine[];
}

export interface DiffFile {
  oldPath: string | null;
  newPath: string | null;
  hunks: DiffHunk[];
}

const HUNK_HEADER = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/;

/** "a/src/x.py\t2024-…" → "src/x.py"; "/dev/null" → null. */
function cleanPath(raw: string, prefix: "a/" | "b/"): string | null {
  const path = raw.split("\t")[0].trim();
  if (path === "/dev/null") return null;
  return path.startsWith(prefix) ? path.slice(prefix.length) : path;
}

export function parseUnifiedDiff(diff: string): DiffFile[] {
  const files: DiffFile[] = [];
  const lines = diff.replace(/\r\n?/g, "\n").split("\n");
  let file: DiffFile | null = null;
  let i = 0;

  try {
    while (i < lines.length) {
      const line = lines[i];

      if (line.startsWith("--- ") && i + 1 < lines.length && lines[i + 1].startsWith("+++ ")) {
        file = {
          oldPath: cleanPath(line.slice(4), "a/"),
          newPath: cleanPath(lines[i + 1].slice(4), "b/"),
          hunks: [],
        };
        files.push(file);
        i += 2;
        continue;
      }

      const match = file ? HUNK_HEADER.exec(line) : null;
      if (!file || !match) {
        // diff --git, index, new file mode, rename lines, stray text: skip.
        i += 1;
        continue;
      }

      const hunk: DiffHunk = {
        header: line,
        oldStart: Number(match[1]),
        oldLines: match[2] === undefined ? 1 : Number(match[2]),
        newStart: Number(match[3]),
        newLines: match[4] === undefined ? 1 : Number(match[4]),
        lines: [],
      };
      file.hunks.push(hunk);
      i += 1;

      let oldLeft = hunk.oldLines;
      let newLeft = hunk.newLines;
      let oldNo = hunk.oldStart;
      let newNo = hunk.newStart;

      while ((oldLeft > 0 || newLeft > 0) && i < lines.length) {
        const body = lines[i];
        // The final "" after a trailing newline is not a line of the hunk.
        if (body === "" && i === lines.length - 1) break;
        i += 1;

        if (body.startsWith("\\")) continue; // "\ No newline at end of file"

        const sign = body === "" ? " " : body[0];
        const text = body.slice(1);
        if (sign === " " && oldLeft > 0 && newLeft > 0) {
          hunk.lines.push({ kind: "context", text, oldLine: oldNo++, newLine: newNo++ });
          oldLeft -= 1;
          newLeft -= 1;
        } else if (sign === "-" && oldLeft > 0) {
          hunk.lines.push({ kind: "del", text, oldLine: oldNo++, newLine: null });
          oldLeft -= 1;
        } else if (sign === "+" && newLeft > 0) {
          hunk.lines.push({ kind: "add", text, oldLine: null, newLine: newNo++ });
          newLeft -= 1;
        } else {
          // Line doesn't fit the header's counts: the hunk is malformed. Stop
          // here and let the outer loop look at this line afresh.
          i -= 1;
          break;
        }
      }
      // A marker right after the last counted line belongs to this hunk.
      while (i < lines.length && lines[i].startsWith("\\")) i += 1;
    }
  } catch {
    // Defensive only; nothing above should throw.
  }

  return files;
}
