-- Base séparée pour les tests automatisés
CREATE DATABASE vigironde_test;
\c vigironde_test
CREATE EXTENSION IF NOT EXISTS postgis;
\c vigironde
CREATE EXTENSION IF NOT EXISTS postgis;
