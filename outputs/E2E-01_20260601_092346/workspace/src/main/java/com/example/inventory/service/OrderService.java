package com.example.inventory.service;

import com.example.inventory.dto.OrderDTO;
import com.example.inventory.dto.OrderItemCreateRequest;
import com.example.inventory.exception.InventoryException;
import com.example.inventory.exception.ResourceNotFoundException;
import com.example.inventory.model.Inventory;
import com.example.inventory.model.Material;
import com.example.inventory.model.Order;
import com.example.inventory.model.OrderItem;
import com.example.inventory.model.enums.OrderStatus;
import com.example.inventory.repository.InventoryRepository;
import com.example.inventory.repository.MaterialRepository;
import com.example.inventory.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final MaterialRepository materialRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(OrderRepository orderRepository, MaterialRepository materialRepository, InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.materialRepository = materialRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public OrderDTO createOrder(OrderDTO.OrderCreateRequest orderCreateRequest) {
        Order order = new Order();
        order.setOrderDate(LocalDateTime.now());
        order.setStatus(OrderStatus.PENDING); // 초기 상태는 PENDING

        List<OrderItem> orderItems = new ArrayList<>();
        for (OrderItemCreateRequest itemRequest : orderCreateRequest.getOrderItems()) {
            Material material = materialRepository.findById(itemRequest.getMaterialId())
                    .orElseThrow(() -> new ResourceNotFoundException("Material not found with id: " + itemRequest.getMaterialId()));

            Inventory inventory = inventoryRepository.findByMaterial_MaterialId(itemRequest.getMaterialId())
                    .orElseThrow(() -> new ResourceNotFoundException("Inventory for material " + material.getName() + " not found."));

            if (inventory.getQuantity() < itemRequest.getQuantity()) {
                throw new InventoryException("Not enough stock for material: " + material.getName() + ". Available: " + inventory.getQuantity() + ", Requested: " + itemRequest.getQuantity());
            }

            // 재고 차감
            inventory.setQuantity(inventory.getQuantity() - itemRequest.getQuantity());
            inventoryRepository.save(inventory);

            OrderItem orderItem = new OrderItem();
            orderItem.setOrder(order);
            orderItem.setMaterial(material);
            orderItem.setQuantity(itemRequest.getQuantity());
            orderItem.setPricePerUnit(itemRequest.getPricePerUnit());
            orderItems.add(orderItem);
        }

        order.setOrderItems(orderItems);
        Order savedOrder = orderRepository.save(order);
        return toDTO(savedOrder);
    }

    @Transactional(readOnly = true)
    public List<OrderDTO> getAllOrders() {
        return orderRepository.findAll().stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    @Transactional(readOnly = true)
    public OrderDTO getOrderById(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found with id: " + id));
        return toDTO(order);
    }

    @Transactional
    public OrderDTO updateOrderStatus(Long id, OrderDTO.OrderUpdateRequest orderUpdateRequest) {
        Order existingOrder = orderRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found with id: " + id));

        existingOrder.setStatus(orderUpdateRequest.getStatus());
        Order updatedOrder = orderRepository.save(existingOrder);
        return toDTO(updatedOrder);
    }

    @Transactional
    public void deleteOrder(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found with id: " + id));

        // 주문 삭제 시 재고 복구 (선택 사항, 비즈니스 로직에 따라 다름)
        // 여기서는 간단히 삭제만 진행. 복구 로직이 필요하면 추가 구현
        orderRepository.delete(order);
    }

    private OrderDTO toDTO(Order order) {
        List<com.example.inventory.dto.OrderItemDTO> itemDTOs = order.getOrderItems().stream()
                .map(item -> new com.example.inventory.dto.OrderItemDTO(
                        item.getOrderItemId(),
                        item.getMaterial().getMaterialId(),
                        item.getQuantity(),
                        item.getPricePerUnit()
                ))
                .collect(Collectors.toList());
        return new OrderDTO(order.getOrderId(), order.getOrderDate(), order.getStatus(), itemDTOs);
    }
}