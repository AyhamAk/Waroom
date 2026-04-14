/* ══════════════════════════════════════════════
   WAR ROOM — JS SYNTAX VALIDATOR
   Validates builder JS before writing to disk.
   On failure: makes a focused fix call to the LLM.
   ══════════════════════════════════════════════ */

const vm = require('vm');
const { createMessage } = require('../llm');

function validateJS(code) {
  try {
    new vm.Script(code);
    return { valid: true, error: null };
  } catch (e) {
    return { valid: false, error: e.message };
  }
}

async function retryBuilderFile({ provider, apiKey, model, brokenCode, error, filename, context }) {
  const prompt = `You are a JavaScript expert. The following code has a syntax error and must be fixed.

FILE: ${filename}
SYNTAX ERROR: ${error}

CONTEXT (what this file is supposed to do):
${context || 'Part of a web application.'}

BROKEN CODE:
${brokenCode}

Output the COMPLETE fixed JavaScript file with the syntax error corrected.
CRITICAL: Output PLAIN JavaScript ONLY — no TypeScript type annotations (x: string, x: number, x: MyType), no interface declarations, no type imports, no generics (<T>), no 'as Type' casts, no access modifiers (public/private/protected). Plain browser-compatible JS.
Do not truncate. Do not add explanations. Output only the fixed code.`;

  try {
    const { text } = await createMessage({
      provider, apiKey, model,
      maxTokens: 6000,
      messages: [{ role: 'user', content: prompt }],
    });
    const stripped = text.trim().replace(/^```[\w]*\n?/, '').replace(/\n?```$/, '');
    return stripped;
  } catch (err) {
    console.error('[validator] retry LLM call failed:', err.message);
    return null;
  }
}

module.exports = { validateJS, retryBuilderFile };
