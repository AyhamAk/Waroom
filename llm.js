/* ══════════════════════════════════════════════
   WAR ROOM — LLM PROVIDER ABSTRACTION
   Supports: 'anthropic' (Claude) | 'gemini' (Google)
   ══════════════════════════════════════════════ */

/* ── Model tiers per provider ── */
const MODELS = {
  anthropic: {
    fast:  'claude-haiku-4-5-20251001',
    smart: 'claude-sonnet-4-6',
  },
  gemini: {
    fast:  'gemini-2.0-flash',
    smart: 'gemini-2.0-flash',
  },
};

function getModels(provider) {
  return MODELS[provider] || MODELS.gemini;
}

/* ══════════════════════════════════════════════
   NON-STREAMING — used by pipeline.js callAgent
   Returns { text, inputTokens, outputTokens }
   ══════════════════════════════════════════════ */
// Singleton Anthropic clients keyed by apiKey — avoid re-instantiating on every call
const _anthropicClients = {};

async function createMessage({ provider, apiKey, model, maxTokens, messages }) {
  if (provider === 'anthropic') {
    const Anthropic = require('@anthropic-ai/sdk');
    const client = _anthropicClients[apiKey] ||
      (_anthropicClients[apiKey] = new Anthropic({ apiKey }));
    const msg = await client.messages.create({ model, max_tokens: maxTokens, messages });
    return {
      text: msg.content[0].text,
      inputTokens:  msg.usage.input_tokens,
      outputTokens: msg.usage.output_tokens,
    };
  }

  if (provider === 'gemini') {
    const { GoogleGenerativeAI } = require('@google/generative-ai');
    const genai = new GoogleGenerativeAI(apiKey);
    const geminiModel = genai.getGenerativeModel({ model });

    // Translate messages array → Gemini parts
    // messages is [{ role: 'user', content: string | array }]
    const lastMsg = messages[messages.length - 1];
    let parts;
    if (Array.isArray(lastMsg.content)) {
      // Multimodal (builder screenshot + text)
      parts = lastMsg.content.map(c => {
        if (c.type === 'image') {
          return { inlineData: { mimeType: c.source.media_type, data: c.source.data } };
        }
        return { text: c.text };
      });
    } else {
      parts = [{ text: lastMsg.content }];
    }

    // Build history (all messages except last)
    const history = messages.slice(0, -1).map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
    }));

    const chat = geminiModel.startChat({ history });
    const result = await chat.sendMessage(parts);
    const response = result.response;
    const text = response.text();
    const usage = response.usageMetadata || {};
    return {
      text,
      inputTokens:  usage.promptTokenCount    || 0,
      outputTokens: usage.candidatesTokenCount || 0,
    };
  }

  throw new Error(`Unknown LLM provider: ${provider}`);
}

/* ══════════════════════════════════════════════
   STREAMING — used by server.js /api/run-agent
   Calls onText(chunk) for each text delta.
   Returns { inputTokens, outputTokens }
   ══════════════════════════════════════════════ */
async function streamMessage({ provider, apiKey, model, maxTokens, system, messages, onText }) {
  if (provider === 'anthropic') {
    const Anthropic = require('@anthropic-ai/sdk');
    const client = new Anthropic({ apiKey });
    const stream = client.messages.stream({ model, max_tokens: maxTokens, system, messages });
    stream.on('text', text => onText(text));
    const msg = await stream.finalMessage();
    return {
      inputTokens:  msg.usage.input_tokens,
      outputTokens: msg.usage.output_tokens,
    };
  }

  if (provider === 'gemini') {
    const { GoogleGenerativeAI } = require('@google/generative-ai');
    const genai = new GoogleGenerativeAI(apiKey);
    // Prepend system prompt as first user turn if provided
    const fullMessages = system
      ? [{ role: 'user', parts: [{ text: `SYSTEM INSTRUCTIONS:\n${system}` }] },
         { role: 'model', parts: [{ text: 'Understood.' }] },
         ...messages.map(m => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] }))]
      : messages.map(m => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] }));

    const lastParts = fullMessages[fullMessages.length - 1].parts;
    const history = fullMessages.slice(0, -1);

    const geminiModel = genai.getGenerativeModel({ model, generationConfig: { maxOutputTokens: maxTokens } });
    const chat = geminiModel.startChat({ history });
    const result = await chat.sendMessageStream(lastParts);

    let inputTokens = 0, outputTokens = 0;
    for await (const chunk of result.stream) {
      const text = chunk.text();
      if (text) onText(text);
    }
    const finalResp = await result.response;
    const usage = finalResp.usageMetadata || {};
    inputTokens  = usage.promptTokenCount    || 0;
    outputTokens = usage.candidatesTokenCount || 0;
    return { inputTokens, outputTokens };
  }

  throw new Error(`Unknown LLM provider: ${provider}`);
}

module.exports = { createMessage, streamMessage, getModels };
