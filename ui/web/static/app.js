const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const promptInput = document.querySelector("#prompt");
const sendButton = document.querySelector("#send");
const status = document.querySelector("#status");
const newSessionButton = document.querySelector("#new-session");
const sessionList = document.querySelector("#session-list");

let sessionId = null;
let sending = false;
const sessionStorageKey = "az.web.session_id";

function appendMessage(role, text = "") {
  const container = document.createElement("article");
  container.className = `message ${role}`;
  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = text;
  container.append(content);
  messages.append(container);
  messages.scrollTop = messages.scrollHeight;
  return content;
}

function appendShellApproval(event, beforeElement = null) {
  const card = document.createElement("article");
  card.className = "message assistant shell-approval";
  const title = document.createElement("strong");
  title.textContent = event.is_background ? "确认启动后台命令" : "确认执行命令";
  const directory = document.createElement("p");
  directory.textContent = `工作目录：${event.working_directory}`;
  const command = document.createElement("pre");
  command.textContent = event.command;
  const actions = document.createElement("div");
  actions.className = "shell-approval-actions";
  const approve = document.createElement("button");
  approve.type = "button";
  approve.textContent = "执行";
  const reject = document.createElement("button");
  reject.type = "button";
  reject.className = "secondary";
  reject.textContent = "取消";
  const decide = async (decision) => {
    approve.disabled = true;
    reject.disabled = true;
    try {
      const response = await fetch(
        `/api/v1/sessions/${sessionId}/shell-approvals/${event.approval_id}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        },
      );
      if (!response.ok) throw new Error("命令审批已失效");
      title.textContent = decision === "approve" ? "已批准执行命令" : "已取消命令执行";
    } catch (error) {
      title.textContent = `审批失败：${error.message}`;
    }
  };
  approve.addEventListener("click", () => decide("approve"));
  reject.addEventListener("click", () => decide("reject"));
  actions.append(approve, reject);
  card.append(title, directory, command, actions);
  messages.insertBefore(card, beforeElement);
  messages.scrollTop = messages.scrollHeight;
}

function appendUsageLimitActions(event) {
  const card = document.createElement("article");
  card.className = "message assistant shell-approval";
  const title = document.createElement("strong");
  title.textContent = "本轮分析达到预算上限";
  const detail = document.createElement("p");
  detail.textContent = event.message;
  const actions = document.createElement("div");
  actions.className = "shell-approval-actions";
  for (const [action, label] of [["continue", "继续分析"], ["summarize", "生成阶段结论"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => sendRecovery(action));
    actions.append(button);
  }
  card.append(title, detail, actions);
  messages.append(card);
}

function setSending(value) {
  sending = value;
  sendButton.disabled = value;
  promptInput.disabled = value;
  newSessionButton.disabled = value;
  sessionList.classList.toggle("is-disabled", value);
  sessionList.querySelectorAll(".session-card").forEach((button) => {
    button.disabled = value;
  });
}

function setSessionStatus(prefix = "会话") {
  status.textContent = `${prefix}：${sessionId}`;
}

function renderMessages(history) {
  messages.replaceChildren();
  if (!history.length) {
    appendMessage("assistant", "你好，我已准备好协助分析当前项目。");
    return;
  }
  for (const message of history) {
    const content = appendMessage(message.role, message.content);
    if (message.html) {
      content.innerHTML = message.html;
      content.classList.add("markdown");
    }
  }
}

async function loadHistory() {
  const response = await fetch(`/api/v1/sessions/${sessionId}/history`);
  if (!response.ok) throw new Error("无法加载会话历史");
  const { messages: history } = await response.json();
  renderMessages(history);
}

function sessionPreview(session) {
  const text = session.first_prompt || "新会话，尚未提问";
  return text.length > 56 ? `${text.slice(0, 56)}…` : text;
}

function renderSessionList(sessions) {
  sessionList.replaceChildren();
  for (const session of sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "session-card";
    button.classList.toggle("active", session.session_id === sessionId);
    button.disabled = sending;
    button.dataset.sessionId = session.session_id;

    const preview = document.createElement("span");
    preview.className = "session-preview";
    preview.textContent = sessionPreview(session);
    const id = document.createElement("span");
    id.className = "session-id";
    id.textContent = session.session_id;
    button.append(preview, id);
    sessionList.append(button);
  }
}

async function refreshSessionList() {
  const response = await fetch("/api/v1/sessions");
  if (!response.ok) throw new Error("无法加载会话列表");
  const { sessions } = await response.json();
  if (!sessions.some((session) => session.session_id === sessionId)) {
    sessions.unshift({ session_id: sessionId, first_prompt: null });
  }
  renderSessionList(sessions);
}

async function activateSession(nextSessionId, prefix = "已切换会话") {
  sessionId = nextSessionId;
  localStorage.setItem(sessionStorageKey, sessionId);
  setSending(true);
  try {
    await Promise.all([loadHistory(), refreshSessionList()]);
    setSessionStatus(prefix);
  } finally {
    setSending(false);
  }
}

async function createSession() {
  setSending(true);
  status.textContent = "正在创建会话…";
  try {
    const response = await fetch("/api/v1/sessions", { method: "POST" });
    if (!response.ok) throw new Error("无法创建会话");
    const { session_id: createdSessionId } = await response.json();
    await activateSession(createdSessionId, "新会话");
  } catch (error) {
    status.textContent = error.message;
    setSending(false);
  }
}

function readSseChunk(chunk, buffer, onEvent) {
  const entries = (buffer + chunk).split("\n\n");
  const remainder = entries.pop();
  for (const entry of entries) {
    const line = entry.split("\n").find((value) => value.startsWith("data: "));
    if (line) onEvent(JSON.parse(line.slice(6)));
  }
  return remainder;
}

async function sendMessage(payload) {
  const response = await fetch(`/api/v1/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) throw new Error("请求失败，请稍后重试");
  const answer = appendMessage("assistant");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let receivedText = false;
  const handleEvent = (event) => {
    if (event.type === "text_delta") {
      receivedText = true;
      answer.textContent += event.delta;
    } else if (event.type === "tool_status") {
      status.textContent = event.message;
    } else if (event.type === "shell_approval_requested") {
      status.textContent = "等待你确认 Shell 命令…";
      // The answer bubble is allocated when the request starts. Put approval
      // cards immediately before it, so text received after the user's choice
      // is rendered below the confirmation instead of above it.
      appendShellApproval(event, answer.parentElement);
    } else if (event.type === "usage_limit_reached") {
      status.textContent = "本轮分析达到预算上限";
      appendUsageLimitActions(event);
    } else if (event.type === "done") {
      status.textContent = "回答完成";
      if (event.html) {
        answer.innerHTML = event.html;
        answer.classList.add("markdown");
      }
    } else if (event.type === "error") {
      status.textContent = `处理失败：${event.message}`;
    }
    messages.scrollTop = messages.scrollHeight;
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer = readSseChunk(decoder.decode(value, { stream: true }), buffer, handleEvent);
  }
  if (!receivedText && !document.querySelector(".shell-approval")) answer.textContent = "本轮未返回可显示的文本。";
  await refreshSessionList();
}

async function sendRecovery(action) {
  if (sending) return;
  setSending(true);
  try {
    await sendMessage({ usage_limit_action: action });
  } catch (error) {
    status.textContent = error.message;
  } finally {
    setSending(false);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = promptInput.value.trim();
  if (!prompt || sending || !sessionId) return;
  appendMessage("user", prompt);
  promptInput.value = "";
  setSending(true);
  status.textContent = "正在分析问题…";
  try {
    await sendMessage({ prompt });
  } catch (error) {
    status.textContent = error.message;
  } finally {
    setSending(false);
  }
});

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

newSessionButton.addEventListener("click", createSession);

sessionList.addEventListener("click", async (event) => {
  const button = event.target.closest(".session-card");
  if (!button || sending || button.dataset.sessionId === sessionId) return;
  try {
    await activateSession(button.dataset.sessionId);
  } catch (error) {
    status.textContent = error.message;
    setSending(false);
  }
});

async function initialize() {
  const savedSessionId = localStorage.getItem(sessionStorageKey);
  try {
    if (savedSessionId) {
      await activateSession(savedSessionId, "已恢复会话");
    } else {
      await createSession();
    }
  } catch (error) {
    status.textContent = error.message;
    setSending(false);
  }
}

initialize();
