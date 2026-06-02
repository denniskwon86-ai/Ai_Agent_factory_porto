<template>
  <div>
    <h2>Products</h2>
    <ul>
      <li v-for="product in products" :key="product.product_id">
        {{ product.product_name }} ({{ product.product_code }} - {{ product.unit_of_measure }})
      </li>
    </ul>
    <p v-if="loading">Loading products...</p>
    <p v-if="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { fetchProducts } from '../services/productService';

interface Product {
  product_id: number;
  product_code: string;
  product_name: string;
  unit_of_measure: string;
}

const products = ref<Product[]>([]);
const loading = ref(true);
const error = ref<string | null>(null);

onMounted(async () => {
  try {
    products.value = await fetchProducts();
  } catch (e: any) {
    error.value = `Failed to fetch products: ${e.message}`;
  } finally {
    loading.value = false;
  }
});
</script>