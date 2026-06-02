<template>
  <div id="app-container">
    <h1>Inventory Management Dashboard</h1>
    <UserList />
    <ProductList />
    <MaterialList />
  </div>
</template>

<script setup lang="ts">
import UserList from './components/UserList.vue';
import ProductList from './components/ProductList.vue';
import MaterialList from './components/MaterialList.vue';
</script>

<style scoped>
#app-container {
  max-width: 960px;
  margin: 40px auto;
  padding: 30px;
  background-color: #ffffff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  display: grid;
  gap: 30px;
}

h1 {
  text-align: center;
  color: #2c3e50;
  margin-bottom: 40px;
  font-size: 2.5em;
  border-bottom: 2px solid #eee;
  padding-bottom: 20px;
}
</style>