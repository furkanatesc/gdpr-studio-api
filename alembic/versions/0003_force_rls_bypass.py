"""force_rls_bypass — FORCE RLS + bypass-GUC policy'leri (gerçek izolasyon)

0002'de kurulan RLS *inert*'ti: uygulama tablo-owner rolüyle bağlanır, owner
RLS'i bypass eder ve migration'da FORCE yoktu. Bu migration:
  - üç tenant tablosunda düz policy'yi bypass-clause'lu policy ile değiştirir,
  - ALTER TABLE ... FORCE ROW LEVEL SECURITY ile owner'ı da RLS'e tabi kılar.

Policy iki yolludur:
    current_setting('app.bypass_rls', true) = 'on'
    OR <col> = current_setting('app.current_org_id', true)::uuid
Normal tenant uçları yalnız app.current_org_id'yi set eder (fail-closed).
Provisioning uçları transaction-local app.bypass_rls='on' set ederek org-ötesi
okuma yapar. USING aynı zamanda INSERT/UPDATE için WITH CHECK olarak hizmet eder.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = [("organizations", "id"), ("memberships", "org_id"), ("invitations", "org_id")]


def upgrade() -> None:
    for tbl, col in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
        # NULLIF(..., '')::uuid: GUC boş string ('') ise NULL'a çevir → karşılaştırma
        # NULL → false (fail-closed), ASLA "invalid input syntax for uuid" hatası verme.
        # Bypass açıkken bile Postgres OR'un her iki yanını değerlendirebildiği için bu
        # null-güvenli cast şarttır (aksi halde residual '' GUC sorguyu patlatır).
        op.execute(
            f"CREATE POLICY {tbl}_isolation ON {tbl} USING ("
            f"current_setting('app.bypass_rls', true) = 'on' "
            f"OR {col} = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")

    # --- Adanmış non-superuser uygulama rolü (kvkk_app) ---
    # FORCE ROW LEVEL SECURITY bir SUPERUSER/BYPASSRLS rolünü RLS'e tabi kılmaz;
    # owner rolü (kvkk) postgres imajında superuser'dır. Bu yüzden uygulama,
    # NOSUPERUSER + NOBYPASSRLS olan ayrı bir rolle (kvkk_app) bağlanmalı ki
    # RLS gerçekten zorlansın. Migration'lar owner (kvkk) ile çalışmaya devam eder.
    #
    # Dev şifresi 'kvkk_app', mevcut dev POSTGRES_PASSWORD=kvkk konvansiyonunu yansıtır.
    # PROD'da bu şifre MUTLAKA döndürülmeli:
    #     ALTER ROLE kvkk_app PASSWORD '<secret>';
    # ve uygulamanın DATABASE_URL'i bu role/şifreye yönlendirilmeli.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'kvkk_app') THEN "
        "CREATE ROLE kvkk_app LOGIN PASSWORD 'kvkk_app' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE; "
        "END IF; END $$;"
    )
    # PG16: public şemasında USAGE varsayılan olarak PUBLIC'e verilmez → açıkça gerekli.
    op.execute("GRANT USAGE ON SCHEMA public TO kvkk_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kvkk_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kvkk_app")
    # GRANT ... ON ALL TABLES yalnız MEVCUT nesneleri kapsayan bir snapshot'tır;
    # gelecek migration'larda owner (kvkk) tarafından oluşturulan tablo/sequence'lar
    # kvkk_app'e otomatik grant'lanmaz → uygulama "permission denied" alır. ALTER
    # DEFAULT PRIVILEGES, owner'ın bundan SONRA oluşturacağı tüm nesnelere grant uygular.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kvkk_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO kvkk_app"
    )


def downgrade() -> None:
    # Önce uygulama rolünü güvenle düşür: grant'ları olan bir rol DROP edilemez,
    # bu yüzden önce tüm yetkileri revoke et.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'kvkk_app') THEN "
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM kvkk_app; "
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM kvkk_app; "
        "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM kvkk_app; "
        "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM kvkk_app; "
        "REVOKE USAGE ON SCHEMA public FROM kvkk_app; "
        "DROP ROLE kvkk_app; "
        "END IF; END $$;"
    )

    # 0002 durumuna dön: FORCE kalksın, düz policy geri gelsin.
    for tbl, col in _TABLES:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_isolation ON {tbl}")
        op.execute(
            f"CREATE POLICY {tbl}_isolation ON {tbl} USING "
            f"({col} = current_setting('app.current_org_id', true)::uuid)"
        )
