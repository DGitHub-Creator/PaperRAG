import { ref, computed } from "vue";

const token = ref(localStorage.getItem("token") || "");
const user = ref(JSON.parse(localStorage.getItem("user") || "{}"));

export function useAuth() {
  const isAuthenticated = computed(() => !!token.value);
  const username = computed(() => user.value.username || "");
  const role = computed(() => user.value.role || "");

  function login(t, u) {
    token.value = t;
    user.value = u;
    localStorage.setItem("token", t);
    localStorage.setItem("user", JSON.stringify(u));
  }

  function logout() {
    token.value = "";
    user.value = {};
    localStorage.removeItem("token");
    localStorage.removeItem("user");
  }

  return { token, user, isAuthenticated, username, role, login, logout };
}
