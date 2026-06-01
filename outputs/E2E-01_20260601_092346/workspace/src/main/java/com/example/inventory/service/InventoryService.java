package com.example.inventory.service;

import com.example.inventory.dto.InventoryDTO;
import com.example.inventory.exception.ResourceNotFoundException;
import com.example.inventory.model.Inventory;
import com.example.inventory.model.Material;
import com.example.inventory.repository.InventoryRepository;
import com.example.inventory.repository.MaterialRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;
    private final MaterialRepository materialRepository;

    public InventoryService(InventoryRepository inventoryRepository, MaterialRepository materialRepository) {
        this.inventoryRepository = inventoryRepository;
        this.materialRepository = materialRepository;
    }

    @Transactional
    public InventoryDTO createInventory(InventoryDTO inventoryDTO) {
        Material material = materialRepository.findById(inventoryDTO.getMaterialId())
                .orElseThrow(() -> new ResourceNotFoundException("Material not found with id: " + inventoryDTO.getMaterialId()));

        Inventory inventory = new Inventory();
        inventory.setMaterial(material);
        inventory.setQuantity(inventoryDTO.getQuantity());
        inventory.setLocation(inventoryDTO.getLocation());
        Inventory savedInventory = inventoryRepository.save(inventory);
        return toDTO(savedInventory);
    }

    @Transactional(readOnly = true)
    public List<InventoryDTO> getAllInventories() {
        return inventoryRepository.findAll().stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public InventoryDTO getInventoryById(Long id) {
        Inventory inventory = inventoryRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Inventory not found with id: " + id));
        return toDTO(inventory);
    }

    @Transactional
    public InventoryDTO updateInventory(Long id, InventoryDTO inventoryDTO) {
        Inventory existingInventory = inventoryRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Inventory not found with id: " + id));

        Material material = materialRepository.findById(inventoryDTO.getMaterialId())
                .orElseThrow(() -> new ResourceNotFoundException("Material not found with id: " + inventoryDTO.getMaterialId()));

        existingInventory.setMaterial(material);
        existingInventory.setQuantity(inventoryDTO.getQuantity());
        existingInventory.setLocation(inventoryDTO.getLocation());
        Inventory updatedInventory = inventoryRepository.save(existingInventory);
        return toDTO(updatedInventory);
    }

    @Transactional
    public void deleteInventory(Long id) {
        if (!inventoryRepository.existsById(id)) {
            throw new ResourceNotFoundException("Inventory not found with id: " + id);
        }
        inventoryRepository.deleteById(id);
    }

    private InventoryDTO toDTO(Inventory inventory) {
        return new InventoryDTO(inventory.getInventoryId(), inventory.getMaterial().getMaterialId(), inventory.getQuantity(), inventory.getLocation());
    }
}