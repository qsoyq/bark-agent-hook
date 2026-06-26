import { spawn } from "node:child_process";
import { appendFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

type JsonRecord = Record<string, unknown>;

const DEBUG_LOG_PATH = join(homedir(), ".bark-agent-hook", "openclaw-plugin-debug.log");
const DEBUG_ENV = "AGENT_BARK_NOTIFY_OPENCLAW_PLUGIN_DEBUG";

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeContext(ctx: unknown): JsonRecord {
  return isRecord(ctx) ? ctx : {};
}

function redactedShape(value: unknown): JsonRecord {
  if (!isRecord(value)) {
    return { type: typeof value };
  }
  return {
    keys: Object.keys(value).sort(),
    channel: typeof value.channel === "string" ? value.channel : undefined,
    channelId: typeof value.channelId === "string" ? value.channelId : undefined,
    hasContent: value.content !== undefined || value.message !== undefined || value.payload !== undefined,
    contentLength:
      typeof value.content === "string"
        ? value.content.length
        : typeof value.message === "string"
          ? value.message.length
          : undefined,
    success: value.success,
  };
}

async function debugLog(event: string, details: JsonRecord = {}): Promise<void> {
  if (process.env[DEBUG_ENV] !== "1") {
    return;
  }
  try {
    await appendFile(
      DEBUG_LOG_PATH,
      `${JSON.stringify({ ts: new Date().toISOString(), event, ...details })}\n`,
      "utf8",
    );
  } catch {
    // Diagnostics must never break hook execution.
  }
}

async function runBarkHook(event: string, payload: JsonRecord): Promise<void> {
  await debugLog("spawn:start", {
    hookEventName: payload.hook_event_name,
    notifyEvent: event,
    payloadShape: redactedShape(payload),
    pathHasBarkAgentHook: process.env.PATH?.includes(".local/bin") ?? false,
  });
  await new Promise<void>((resolve) => {
    const child = spawn(
      "bark-agent-hook",
      ["hook", "--runtime", "openclaw", "--event", event, "--summary-mode", "extract"],
      { stdio: ["pipe", "ignore", "ignore"] },
    );

    child.on("error", async (error: NodeJS.ErrnoException) => {
      await debugLog("spawn:error", {
        hookEventName: payload.hook_event_name,
        code: error.code,
        message: error.message,
      });
      resolve();
    });
    child.on("close", async (code, signal) => {
      await debugLog("spawn:close", {
        hookEventName: payload.hook_event_name,
        code,
        signal,
      });
      resolve();
    });
    child.stdin.end(JSON.stringify(payload));
  });
}

function eventContent(event: unknown): unknown {
  if (!isRecord(event)) {
    return undefined;
  }
  if (event.content !== undefined) {
    return event.content;
  }
  if (event.message !== undefined) {
    return event.message;
  }
  if (event.payload !== undefined) {
    return event.payload;
  }
  return undefined;
}

export default definePluginEntry({
  id: "bark-agent-hook-openclaw",
  name: "Agent Bark Notify",
  description: "Send Bark notifications from OpenClaw lifecycle hooks through bark-agent-hook.",
  register(api) {
    void debugLog("register");
    api.on(
      "agent_end",
      async (event, ctx) => {
        await debugLog("hook:agent_end", {
          eventShape: redactedShape(event),
          contextShape: redactedShape(ctx),
        });
        const context = normalizeContext(ctx);
        await runBarkHook(event.success ? "completion" : "failed", {
          source: "openclaw",
          hook_event_name: "agent_end",
          success: event.success,
          error: event.error,
          durationMs: event.durationMs,
          runId: event.runId ?? context.runId,
          sessionId: context.sessionId,
          sessionKey: context.sessionKey,
          agentId: context.agentId,
          workspaceDir: context.workspaceDir,
          channel: context.channel,
          messageProvider: context.messageProvider,
        });
      },
      { priority: -100, timeoutMs: 5000 },
    );

    api.on(
      "message_sent",
      async (event, ctx) => {
        await debugLog("hook:message_sent", {
          eventShape: redactedShape(event),
          contextShape: redactedShape(ctx),
        });
        if (event.success === false) {
          await debugLog("hook:message_sent:skip_failed");
          return;
        }
        const context = normalizeContext(ctx);
        await runBarkHook("completion", {
          source: "openclaw",
          hook_event_name: "message_sent",
          success: event.success,
          content: eventContent(event),
          channelId: event.channelId ?? context.channelId,
          accountId: event.accountId ?? context.accountId,
          conversationId: event.conversationId ?? context.conversationId,
          messageId: event.messageId ?? context.messageId,
          sessionId: context.sessionId,
          sessionKey: event.sessionKey ?? context.sessionKey,
          agentId: context.agentId,
          workspaceDir: context.workspaceDir,
          channel: context.channel,
          messageProvider: context.messageProvider,
        });
      },
      { priority: -100, timeoutMs: 5000 },
    );
  },
});
