import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/dist/index.css'
import App from './App.vue'
import './styles/main.css'

createApp(App).use(createPinia()).mount('#app')
