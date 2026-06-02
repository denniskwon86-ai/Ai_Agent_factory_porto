<template>
  <div>
    <h2>Materials</h2>
    <ul>
      <li v-for="material in materials" :key="material.material_id">
        {{ material.material_name }} ({{ material.material_code }} - {{ material.unit_of_measure }})
      </li>
    </ul>
    <p v-if="loading">Loading materials...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchMaterials } from '../services/materialService';

interface Material {
  material_id: number;
  material_code: string;
  material_name: string;
  unit_of_measure: string;
}

const materials = ref<Material[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    materials.value = await fetchMaterials();
  } catch (e: any) {
    error.value = `Failed to fetch materials: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>