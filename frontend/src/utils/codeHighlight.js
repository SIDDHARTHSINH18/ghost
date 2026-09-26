/**
 * Lightweight, dependency-free syntax highlighter for ENMA chat
 * code blocks. Produces spans with token classes that App.css
 * colors using the existing ENMA cyan theme — no second color
 * system is introduced.
 *
 * Supported languages: python, javascript, typescript, jsx, tsx,
 * html, css, json, powershell, bash/shell, sql, yaml, markdown.
 * Unknown languages fall back to strings/numbers/comments.
 */

const KEYWORDS = {
  python:
    "False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield|self|match|case",
  javascript:
    "as|async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|from|function|get|if|import|in|instanceof|let|new|of|return|set|static|super|switch|this|throw|try|typeof|var|void|while|with|yield|true|false|null|undefined",
  typescript:
    "abstract|any|as|async|await|boolean|break|case|catch|class|const|constructor|continue|declare|default|delete|do|else|enum|export|extends|finally|for|from|function|get|if|implements|import|in|infer|instanceof|interface|is|keyof|let|namespace|never|new|number|of|private|protected|public|readonly|return|satisfies|set|static|string|super|switch|this|throw|try|type|typeof|undefined|unknown|var|void|while|yield|true|false|null",
  css: "important|media|keyframes|supports|layer|from|to",
  json: "true|false|null",
  powershell:
    "begin|break|catch|class|continue|data|do|dynamicparam|else|elseif|end|exit|filter|finally|for|foreach|from|function|hidden|if|in|param|process|return|switch|throw|trap|try|until|using|var|while|True|False|Null",
  bash:
    "if|then|else|elif|fi|for|while|until|do|done|case|esac|in|function|select|break|continue|return|exit|local|export|readonly|declare|set|unset|shift|source|alias|echo|cd|true|false",
  sql: "ADD|ALL|ALTER|AND|ANY|AS|ASC|BEGIN|BETWEEN|BY|CASE|COMMIT|CREATE|CROSS|DEFAULT|DELETE|DESC|DISTINCT|DROP|ELSE|END|EXISTS|FROM|FULL|GROUP|HAVING|IN|INNER|INSERT|INTO|IS|JOIN|KEY|LEFT|LIKE|LIMIT|NOT|NULL|OFFSET|ON|OR|ORDER|OUTER|PRIMARY|RIGHT|ROLLBACK|SELECT|SET|TABLE|THEN|TOP|TRANSACTION|UNION|UPDATE|VALUES|VIEW|WHEN|WHERE|WITH",
  yaml: "true|false|null|yes|no|on|off",
  markdown: "",
};

const ALIASES = {
  py: "python",
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  jsx: "javascript",
  tsx: "typescript",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  ps: "powershell",
  ps1: "powershell",
  psm1: "powershell",
  yml: "yaml",
  md: "markdown",
  htm: "html",
  xml: "html",
  scss: "css",
  less: "css",
  plaintext: "text",
  "": "text",
};

// One combined pattern per highlight pass: comments, strings,
// numbers, keywords, function calls, types/classes. Groups are
// positional so the tokenizer can classify each match.
const PATTERN_CACHE = new Map();

function patternFor(language) {
  if (PATTERN_CACHE.has(language)) {
    return PATTERN_CACHE.get(language);
  }

  const kw = KEYWORDS[language];

  const parts = [
    // Comments (language-appropriate forms; extra forms are
    // harmless because they cannot start inside other tokens
    // except SQL-style "--", which is why it is listed only
    // for sql/yaml).
    language === "sql"
      ? "(--[^\\n]*)"
      : language === "html"
       ? "(<!--[\\s\\S]*?-->)"
        : language === "css" ||
            language === "javascript" ||
            language === "typescript"
          ? "(//[^\\n]*|/\\*[\\s\\S]*?\\*/)"
          : "(#[^\\n]*)",
    // Strings.
    "(\"(?:[^\"\\\\\\n]|\\\\.)*\"|'(?:[^'\\\\\\n]|\\\\.)*'|`(?:[^`\\\\]|\\\\.)*`)",
    // Numbers (including hex and simple version-like decimals).
    "(\\b0[xX][0-9a-fA-F]+\\b|\\b\\d+(?:\\.\\d+)?\\b)",
    // Keywords.
    kw ? `\\b(${kw})\\b` : "(\\u0000)",
    // Function calls / named invocations.
    "(\\b[A-Za-z_$][\\w$]*(?=\\s*\\())",
    // Types / classes / HTML tags / YAML keys.
    language === "html"
      ? "(</?[A-Za-z][\\w-]*)"
      : language === "yaml"
        ? "(^[ \\t]*[-]?[ \\t]*[A-Za-z_][\\w.-]*)(?=\\s*:)"
        : "(\\b[A-Z][A-Za-z0-9_]*\\b)",
  ];

  const pattern = new RegExp(parts.join("|"), "gm");

  PATTERN_CACHE.set(language, pattern);

  return pattern;
}

export function normalizeLanguage(language) {
  const raw = (language || "").trim().toLowerCase();

  return ALIASES[raw] !== undefined ? ALIASES[raw] : raw;
}

// Group index -> token class. Index 0 is the whole match.
const GROUP_CLASS = [
  null,
  "tok-comment",
  "tok-string",
  "tok-number",
  "tok-keyword",
  "tok-function",
  "tok-type",
];

/**
 * Tokenize code into [{text, className|null}] segments.
 * Plain segments have className null.
 */
export function highlightSegments(code, language) {
  const lang = normalizeLanguage(language);

  if (lang === "text" || lang === "markdown") {
    return [{ text: code, className: null }];
  }

  const segments = [];
  const pattern = patternFor(lang);

  pattern.lastIndex = 0;

  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(code)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        text: code.slice(lastIndex, match.index),
        className: null,
      });
    }

    let className = null;

    for (let group = 1; group < match.length; group += 1) {
      if (match[group] !== undefined) {
        className = GROUP_CLASS[group];
        break;
      }
    }

    segments.push({ text: match[0], className });

    lastIndex = match.index + match[0].length;

    // Guard against zero-length matches looping forever.
    if (match[0].length === 0) {
      pattern.lastIndex += 1;
    }
  }

  if (lastIndex < code.length) {
    segments.push({ text: code.slice(lastIndex), className: null });
  }

  return segments;
}
