import { createRouter, createWebHistory } from 'vue-router'
import Step1Inspire from '../views/Step1Inspire.vue'
import Step2Settings from '../views/Step2Settings.vue'
import Step3Script from '../views/Step3Script.vue'
import Step4Preview from '../views/Step4Preview.vue'
import VideoGeneration from '../views/VideoGeneration.vue'
import SettingsView from '../views/SettingsView.vue'
import HistoryView from '../views/HistoryView.vue'
import { useStoryStore } from '../stores/story.js'
import { canAccessStep, getStepRedirectPath } from '../utils/stepAccess.js'

const routes = [
  { path: '/', redirect: '/step1' },
  { path: '/step1', component: Step1Inspire, meta: { step: 1 } },
  { path: '/step2', component: Step2Settings, meta: { step: 2 } },
  { path: '/step3', component: Step3Script, meta: { step: 3 } },
  { path: '/step4', component: Step4Preview, meta: { step: 4 } },
  { path: '/video-generation', component: VideoGeneration, meta: { step: 5 } },
  { path: '/settings', component: SettingsView },
  { path: '/history', component: HistoryView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const targetStep = to.meta?.step
  if (!targetStep) return true

  const store = useStoryStore()
  if (canAccessStep(store, targetStep)) {
    store.setStep(targetStep)
    return true
  }

  const redirectPath = getStepRedirectPath(store, targetStep)
  const redirectStep = routes.find(route => route.path === redirectPath)?.meta?.step
  if (redirectStep) {
    store.setStep(redirectStep)
  }
  return redirectPath
})

export default router
