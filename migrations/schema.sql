-- ============================================================
-- Yakero Ecommerce — Esquema de Base de Datos
-- Compatible con MySQL Workbench 8.x
-- Charset: utf8mb4 | Collation: utf8mb4_unicode_ci
-- ============================================================

CREATE DATABASE IF NOT EXISTS yakero_ecommerce
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE yakero_ecommerce;

-- ─────────────────────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE users (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email           VARCHAR(255) NOT NULL UNIQUE,
  password_hash   VARCHAR(255) NOT NULL,
  first_name      VARCHAR(100) NOT NULL,
  last_name       VARCHAR(100) NOT NULL,
  phone           VARCHAR(30),
  role            ENUM('customer','admin','pos_service') NOT NULL DEFAULT 'customer',
  is_active       TINYINT(1) NOT NULL DEFAULT 1,
  is_guest        TINYINT(1) NOT NULL DEFAULT 0,
  points_balance  INT NOT NULL DEFAULT 0,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_users_email (email)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- ADDRESSES
-- ─────────────────────────────────────────────────────────────
CREATE TABLE addresses (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED,
  label       VARCHAR(100) NOT NULL,
  street      VARCHAR(200) NOT NULL,
  number      VARCHAR(20)  NOT NULL,
  commune     VARCHAR(100) NOT NULL,
  city        VARCHAR(100) NOT NULL,
  latitude    DOUBLE,
  longitude   DOUBLE,
  notes       TEXT,
  is_default  TINYINT(1) NOT NULL DEFAULT 0,
  CONSTRAINT fk_addr_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- CATEGORIES
-- ─────────────────────────────────────────────────────────────
CREATE TABLE categories (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(100) NOT NULL,
  slug        VARCHAR(120) NOT NULL UNIQUE,
  ticket_tag  ENUM('cocina_sushi','cocina_sandwich','caja','ninguna') NOT NULL,
  image_url   VARCHAR(500),
  sort_order  INT NOT NULL DEFAULT 0,
  is_active   TINYINT(1) NOT NULL DEFAULT 1,
  INDEX idx_cat_slug (slug)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- PRODUCTS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE products (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  category_id  INT UNSIGNED NOT NULL,
  sku          VARCHAR(50) UNIQUE,
  name         VARCHAR(200) NOT NULL,
  slug         VARCHAR(220) NOT NULL UNIQUE,
  description  TEXT,
  price        DECIMAL(10,0) NOT NULL,
  image_url    VARCHAR(500),
  ticket_tag   ENUM('cocina_sushi','cocina_sandwich','caja','ninguna') NOT NULL,
  is_available TINYINT(1) NOT NULL DEFAULT 1,
  sort_order   INT NOT NULL DEFAULT 0,
  CONSTRAINT fk_prod_cat FOREIGN KEY (category_id)
    REFERENCES categories(id),
  INDEX idx_prod_slug (slug),
  INDEX idx_prod_sku  (sku)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- MODIFIER GROUPS  (grupos de modificadores: proteína, salsa, etc.)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE modifier_groups (
  id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  product_id          INT UNSIGNED,
  promotion_slot_id   INT UNSIGNED,
  name                VARCHAR(100) NOT NULL,
  modifier_type       ENUM('single','multiple') NOT NULL DEFAULT 'single',
  min_selections      INT NOT NULL DEFAULT 1,
  max_selections      INT NOT NULL DEFAULT 1,
  is_required         TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_mg_product FOREIGN KEY (product_id)
    REFERENCES products(id) ON DELETE CASCADE,
  -- fk a promotion_slots se agrega después de crear esa tabla
  CHECK (product_id IS NOT NULL OR promotion_slot_id IS NOT NULL)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- MODIFIER OPTIONS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE modifier_options (
  id           INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  group_id     INT UNSIGNED NOT NULL,
  name         VARCHAR(100) NOT NULL,
  extra_price  DECIMAL(10,0) NOT NULL DEFAULT 0,
  is_available TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_mo_group FOREIGN KEY (group_id)
    REFERENCES modifier_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- PROMOTIONS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE promotions (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(200) NOT NULL,
  description     TEXT,
  promotion_type  VARCHAR(50)  NOT NULL,   -- 'bundle','fixed','percent','coupon'
  value           DECIMAL(10,0) NOT NULL,
  image_url       VARCHAR(500),
  is_active       TINYINT(1) NOT NULL DEFAULT 1,
  starts_at       DATETIME,
  ends_at         DATETIME,
  INDEX idx_promo_active (is_active, ends_at)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- PROMOTION SLOTS  (slots configurables dentro de un bundle)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE promotion_slots (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  promotion_id  INT UNSIGNED NOT NULL,
  slot_name     VARCHAR(200) NOT NULL,
  pieces        INT NOT NULL DEFAULT 1,
  ticket_tag    ENUM('cocina_sushi','cocina_sandwich','caja','ninguna') NOT NULL,
  CONSTRAINT fk_slot_promo FOREIGN KEY (promotion_id)
    REFERENCES promotions(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Ahora que promotion_slots existe, agregar FK en modifier_groups
ALTER TABLE modifier_groups
  ADD CONSTRAINT fk_mg_slot FOREIGN KEY (promotion_slot_id)
    REFERENCES promotion_slots(id) ON DELETE CASCADE;

-- ─────────────────────────────────────────────────────────────
-- COUPONS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE coupons (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code             VARCHAR(50)   NOT NULL UNIQUE,
  discount_type    ENUM('fixed','percent') NOT NULL,
  discount_value   DECIMAL(10,2) NOT NULL,
  min_order_amount DECIMAL(10,0) NOT NULL DEFAULT 0,
  max_uses         INT,
  uses_count       INT NOT NULL DEFAULT 0,
  user_id          INT UNSIGNED,   -- NULL = cupón público
  expires_at       DATETIME,
  is_active        TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT fk_coupon_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE SET NULL,
  INDEX idx_coupon_code (code)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- ORDERS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE orders (
  id                        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id                   INT UNSIGNED,
  guest_email               VARCHAR(255),
  guest_phone               VARCHAR(30),
  address_id                INT UNSIGNED,
  delivery_type             ENUM('delivery','retiro') NOT NULL,
  status                    ENUM('pendiente','pagado','en_preparacion','listo',
                                 'despachado','entregado','cancelado','anulado')
                            NOT NULL DEFAULT 'pendiente',
  payment_status            ENUM('pendiente','pagado','rechazado','reembolso')
                            NOT NULL DEFAULT 'pendiente',
  subtotal                  DECIMAL(10,0) NOT NULL,
  delivery_fee              DECIMAL(10,0) NOT NULL DEFAULT 0,
  discount                  DECIMAL(10,0) NOT NULL DEFAULT 0,
  points_used               INT NOT NULL DEFAULT 0,
  total                     DECIMAL(10,0) NOT NULL,
  mp_preference_id          VARCHAR(255),
  mp_payment_id             VARCHAR(255),
  mp_payment_status         VARCHAR(50),
  notes                     TEXT,
  delivery_address_snapshot JSON,          -- snapshot inmutable de dirección
  created_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at                   DATETIME,
  ready_at                  DATETIME,
  delivered_at              DATETIME,
  CONSTRAINT fk_order_user    FOREIGN KEY (user_id)    REFERENCES users(id)     ON DELETE SET NULL,
  CONSTRAINT fk_order_address FOREIGN KEY (address_id) REFERENCES addresses(id) ON DELETE SET NULL,
  INDEX idx_order_status      (status),
  INDEX idx_order_mp_pref     (mp_preference_id),
  INDEX idx_order_mp_pay      (mp_payment_id),
  INDEX idx_order_user        (user_id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- ORDER ITEMS
-- ─────────────────────────────────────────────────────────────
CREATE TABLE order_items (
  id                INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_id          INT UNSIGNED NOT NULL,
  product_id        INT UNSIGNED,
  promotion_id      INT UNSIGNED,
  promotion_slot_id INT UNSIGNED,
  product_name      VARCHAR(200) NOT NULL,   -- snapshot del nombre
  quantity          INT NOT NULL DEFAULT 1,
  unit_price        DECIMAL(10,0) NOT NULL,
  total_price       DECIMAL(10,0) NOT NULL,
  ticket_tag        ENUM('cocina_sushi','cocina_sandwich','caja','ninguna') NOT NULL,
  notes             TEXT,
  config_json       JSON,                    -- snapshot config para POS/impresión
  CONSTRAINT fk_oi_order     FOREIGN KEY (order_id)     REFERENCES orders(id)     ON DELETE CASCADE,
  CONSTRAINT fk_oi_product   FOREIGN KEY (product_id)   REFERENCES products(id)   ON DELETE SET NULL,
  CONSTRAINT fk_oi_promo     FOREIGN KEY (promotion_id) REFERENCES promotions(id) ON DELETE SET NULL,
  INDEX idx_oi_order (order_id),
  INDEX idx_oi_tag   (ticket_tag)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- ORDER ITEM MODIFIERS  (snapshot inmutable de modificadores elegidos)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE order_item_modifiers (
  id                  INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  order_item_id       INT UNSIGNED NOT NULL,
  modifier_option_id  INT UNSIGNED,           -- nullable: si la opción fue borrada
  option_name         VARCHAR(100) NOT NULL,  -- snapshot del nombre
  group_name          VARCHAR(100) NOT NULL,  -- snapshot del grupo
  extra_price         DECIMAL(10,0) NOT NULL DEFAULT 0,
  CONSTRAINT fk_oim_item   FOREIGN KEY (order_item_id)      REFERENCES order_items(id)      ON DELETE CASCADE,
  CONSTRAINT fk_oim_option FOREIGN KEY (modifier_option_id) REFERENCES modifier_options(id) ON DELETE SET NULL,
  INDEX idx_oim_item (order_item_id)
) ENGINE=InnoDB;

-- ─────────────────────────────────────────────────────────────
-- SEED: Categorías base de Yakero
-- ─────────────────────────────────────────────────────────────
INSERT INTO categories (name, slug, ticket_tag, sort_order) VALUES
  ('Rolls',           'rolls',           'cocina_sushi',    1),
  ('Especial Rolls',  'especial-rolls',  'cocina_sushi',    2),
  ('Hand Rolls',      'hand-rolls',      'cocina_sushi',    3),
  ('Gohan',           'gohan',           'cocina_sushi',    4),
  ('Gyosas',          'gyosas',          'cocina_sushi',    5),
  ('Comida Casera',   'comida-casera',   'cocina_sandwich', 6),
  ('Postres',         'postres',         'caja',            7),
  ('Bebidas',         'bebidas',         'caja',            8);
