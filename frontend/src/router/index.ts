import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "home",
    component: () => import("@/views/HomeView.vue"),
  },
  {
    path: "/bookmarks",
    name: "bookmarks",
    component: () => import("@/views/BookmarksView.vue"),
  },
  {
    path: "/ticker/:symbol",
    name: "ticker",
    component: () => import("@/views/TickerView.vue"),
    props: true,
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 };
  },
});
