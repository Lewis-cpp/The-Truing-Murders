import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import './styles/main.css'
import './styles/theme.css'

createApp(App).use(createPinia()).mount('#app')
