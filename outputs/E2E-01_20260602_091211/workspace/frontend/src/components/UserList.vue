<template>
  <div>
    <h2>Users</h2>
    <ul>
      <li v-for="user in users" :key="user.user_id">
        {{ user.username }} ({{ user.email }} - {{ user.role }})
      </li>
    </ul>
    <p v-if="loading">Loading users...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchUsers } from '../services/userService';

interface User {
  user_id: number;
  username: string;
  email: string;
  role: string;
}

const users = ref<User[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    users.value = await fetchUsers();
  } catch (e: any) {
    error.value = `Failed to fetch users: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>