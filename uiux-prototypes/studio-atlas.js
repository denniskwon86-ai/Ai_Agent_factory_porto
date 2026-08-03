(() => {
  "use strict";

  document.querySelectorAll(".studio-atlas").forEach(atlas => {
    const chat = atlas.querySelector("[data-atlas-chat]");
    const input = atlas.querySelector("[data-atlas-input]");
    const send = atlas.querySelector("[data-atlas-send]");
    if (!chat || !input || !send) return;

    function addMessage(text, role) {
      const message = document.createElement("p");
      message.className = `studio-atlas-message ${role}`;
      message.textContent = text;
      chat.appendChild(message);
      chat.scrollTop = chat.scrollHeight;
    }

    function reply(question, answer) {
      addMessage(question, "user");
      window.setTimeout(() => addMessage(answer || "현재 화면의 상태·근거·선택지를 함께 확인해 다음 행동을 제안하겠습니다. 이 대화는 특정 Task ID가 없어도 전체 시스템 컨텍스트를 기준으로 동작합니다.", "agent"), 160);
    }

    atlas.querySelectorAll("[data-atlas-prompt]").forEach(button => {
      button.addEventListener("click", () => reply(button.textContent.trim(), button.dataset.answer));
    });

    function submit() {
      const question = input.value.trim();
      if (!question) return;
      input.value = "";
      reply(question, atlas.dataset.defaultAnswer);
    }

    send.addEventListener("click", submit);
    input.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submit();
      }
    });
  });
})();
