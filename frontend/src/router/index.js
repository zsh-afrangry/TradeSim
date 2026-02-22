import { createRouter, createWebHistory } from 'vue-router'
import Simulator from '../views/Simulator.vue'
import Dashboard from '../views/Dashboard.vue'

const routes = [
    {
        path: '/',
        redirect: '/simulate'
    },
    {
        path: '/simulate',
        name: 'Simulate',
        component: Simulator
    },
    {
        path: '/dashboard',
        name: 'Dashboard',
        component: Dashboard
    },
    {
        path: '/detail/:id',
        name: 'Detail',
        component: () => import('../views/Detail.vue')
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

export default router
