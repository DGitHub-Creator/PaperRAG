<template>
  <div class="auth-shell">
    <section class="auth-hero">
      <div class="hero-brand">
        <div class="mark">R</div>
        <span>{{ $t("app.short_title") }}</span>
      </div>
      <h1>{{ $t("auth.hero_title") }}</h1>
      <p class="hero-desc">{{ $t("auth.hero_desc") }}</p>
      <ul class="hero-points">
        <li v-for="key in points" :key="key">
          <Icon name="check" :size="15" />
          <span>{{ $t(key) }}</span>
        </li>
      </ul>
      <div class="hero-foot">{{ $t("auth.hero_foot") }}</div>
    </section>

    <section class="auth-main">
      <div class="auth-card card">
        <AuthPanel @authenticated="handleAuthenticated" />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from "vue-router"
import AuthPanel from "../components/AuthPanel.vue"
import Icon from "../components/Icon.vue"
import { useAuth } from "../composables/useAuth"
import { useAppSession } from "../composables/useAppSession"

const router = useRouter()
const route = useRoute()
const { token } = useAuth()
const { onSignedIn } = useAppSession()

const points = ["auth.point_retrieval", "auth.point_evidence", "auth.point_workspace"]

function handleAuthenticated(): void {
  onSignedIn(token.value)
  const redirect = typeof route.query.redirect === "string" ? route.query.redirect : ""
  void router.replace(redirect || { name: "chat" })
}
</script>

<style scoped>
.auth-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  height: 100vh;
  background: var(--bg-app);
}

.auth-hero {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 14px;
  padding: 56px 60px;
  background:
    radial-gradient(1000px 460px at 12% 8%, rgba(47, 111, 237, .28), transparent 62%),
    radial-gradient(760px 420px at 92% 96%, rgba(109, 74, 255, .26), transparent 60%),
    var(--rail-bg);
  color: #cfd9e6;
}
.hero-brand { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.hero-brand .mark {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: linear-gradient(135deg, var(--accent), #6d4aff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.hero-brand span { color: #fff; font-weight: 600; font-size: 15px; letter-spacing: .01em; }
.auth-hero h1 { color: #fff; font-size: 27px; line-height: 1.3; max-width: 15em; }
.hero-desc { font-size: 13.5px; line-height: 1.7; max-width: 32em; color: #a9b8ca; }
.hero-points { list-style: none; display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
.hero-points li { display: flex; align-items: center; gap: 9px; font-size: 13px; }
.hero-points li :deep(.rp-icon) { color: #5b8ff5; }
.hero-foot { margin-top: 20px; font-size: 11.5px; color: #5d6f86; }

.auth-main { display: flex; align-items: center; justify-content: center; padding: 40px 28px; }
.auth-card { width: 100%; max-width: 380px; padding: 28px 26px; box-shadow: var(--shadow); }

@media (max-width: 900px) {
  .auth-shell { grid-template-columns: minmax(0, 1fr); }
  .auth-hero { display: none; }
}
</style>
