/** Quote flowchart labels containing array subscripts or comparison operators.
 * This only encodes labels; the original source remains stored unchanged.
 */
export function normalizeMermaidSource(source: string): string {
  if (!/^\s*(flowchart|graph)\b/m.test(source)) return source
  return source.split('\n').map(line => {
    const pattern = /\b[A-Za-z_][\w-]*\s*([\[{])/g
    let result = ''; let cursor = 0
    while (pattern.exec(line)) {
      const start = pattern.lastIndex - 1
      const opening = line[start]!; const closing = opening === '[' ? ']' : '}'
      let depth = 1; let end = start + 1
      for (; end < line.length && depth; end++) {
        if (line[end] === opening) depth++
        if (line[end] === closing) depth--
      }
      if (depth) continue
      const label = line.slice(start + 1, end - 1)
      if (/^["']/.test(label.trim()) || label.startsWith(opening)) { pattern.lastIndex = end; continue }
      result += line.slice(cursor, start + 1) + '"' + label.replace(/"/g, '&quot;') + '"' + closing
      cursor = end; pattern.lastIndex = end
    }
    return result + line.slice(cursor)
  }).join('\n')
}
