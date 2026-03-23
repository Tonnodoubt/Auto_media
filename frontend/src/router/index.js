import { createRouter, createWebHistory } from 'vue-router'
import Step1Inspire from '../views/Step1Inspire.vue'
import Step2Settings from '../views/Step2Settings.vue'
import Step3Script from '../views/Step3Script.vue'
import Step4Preview from '../views/Step4Preview.vue'
import VideoGeneration from '../views/VideoGeneration.vue'
import SettingsView from '../views/SettingsView.vue'
import HistoryView from '../views/HistoryView.vue'

const routes = [
  { path: '/', redirect: '/step1' },
  { path: '/step1', component: Step1Inspire },
  { path: '/step2', component: Step2Settings },
  { path: '/step3', component: Step3Script },
  { path: '/step4', component: Step4Preview },
  { path: '/video-generation', component: VideoGeneration },
  { path: '/settings', component: SettingsView },
  { path: '/history', component: HistoryView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
