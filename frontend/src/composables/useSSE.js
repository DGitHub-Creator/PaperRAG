import { ref } from "vue";
import api from "../services/api.js";

export function useSSE() {
  const abortController = ref(null);

  function sendMessage(question, onChunk) {
    abortController.value = new AbortController();
    const token = localStorage.getItem("token");
    const params = new URLSearchParams({ question, session_id: crypto.randomUUID() });
    fetch(`/api/chat/stream?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: abortController.value.signal,
    })
      .then((res) => {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        function read() {
          reader.read().then(({ done, value }) => {
            if (done) return;
            const text = decoder.decode(value);
            for (const line of text.split("\n")) {
              if (line.startsWith("data: ")) onChunk(line.slice(6));
            }
            read();
          });
        }
        read();
      })
      .catch(() => {});
  }

  function abort() {
    abortController.value?.abort();
  }

  return { sendMessage, abort };
}
