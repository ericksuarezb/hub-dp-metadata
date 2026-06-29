-- ___________________________________________________________________________________________________________________________________
--/     #####   PROYECTO CRYSTAL DATA   #####
--| @FECHA DE CREACION:
--|     # Martes, 24 de Febrero del 2026
--| @DOMINIOS:                          
--|     # Captacion
--| @ARCHIVO:                           
--|     # 01_cd_cap_cuenta_delta.sql 
--| @AUTOR:                                     
--|     # Erick Suarez Buendia <erick.suarez@algorithia.com>
--|	# Brenda Sarahi Rosas Morán <brenda.rosasm@algorithia.com>
--| @DESCRIPCION:                        
--|     # 
--| @TIEMPOS DE EJECUCION:      
--|     # 
--| @MODIFICACIONES:
--|             # @FECHA                
--|             # @DESCRIPCION
--|     # 
--| @PARAMETROS
--|     # ${esquema_cd} = wc_ec_cd_baz_bdclientes
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--\____________________________________________________________________________________________________________________________________/

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_portafolio_cuentas_activas
--drop TABLE ${esquema_cu}.cu_cap_portafolio_cuentas_activas;
--create TABLE ${esquema_cu}.cu_cap_portafolio_cuentas_activas stored as parquet as
SELECT 
     if(CTA.cod_sistema = 'ALNOVA',CTA.id_cliente,FIN.id_cliente_alnova) as id_cliente_alnova
    ,if(CTA.cod_sistema = 'FINACLE',CTA.id_cliente,CTE.id_cliente_finacle) as id_cliente_finacle
    ,coalesce(CTE.id_cliente_unico ,FIN.id_cliente_unico) as id_cliente_unico
    ,coalesce(CTE.id_icu_digital ,FIN.id_icu_digital) as id_icu_digital
    ,CTA.cod_tipo_persona
    ,CTA.id_cuenta
    ,CTA.id_sucursal_apertura
    ,CTA.id_sucursal_gestora
    ,CTA.desc_cod_titular
    ,CTA.cod_estatus
    ,CTA.fec_apertura
    ,CTA.fec_cancelacion
    ,CTA.cod_bloqueo
    ,CTA.cod_tipo_moneda
    ,CTA.fec_ultima_txn
    ,CTA.id_sucursal_ultima_txn
    ,CTA.cod_usuario_ultima_txn
    ,CTA.num_ultima_txn
    ,CTA.num_dias_inactividad
    ,CTA.ind_cuenta_nueva
    ,CTA.num_dias_antiguedad
    ,PRD.cod_producto
    ,PRD.cod_familia_producto
    ,PRD.cod_nivel_cuenta
    ,PRD.cod_producto_nivel_01
    ,PRD.cod_producto_nivel_02
    ,PRD.cod_producto_nivel_03
    ,PRD.cod_producto_nivel_04
    ,PRD.cod_producto_nivel_05
    ,PRD.cod_producto_nivel_06
    ,PRD.cod_producto_nivel_07
    ,CTA.sld_actual
    ,coalesce(SLD.sld_disponible ,0) as sld_disponible
    ,SLD.cod_sld_disponible
    ,CURRENT_TIMESTAMP() AS FEC_CARGA
    ,CTA.cod_sistema
FROM ${esquema_cu}.cu_cap_universo_cuentas CTA
LEFT JOIN ${esquema_cd}.cd_cap_relacion_cliente CTE on
	CTA.id_cliente = CTE.id_cliente_alnova AND CTE.cod_sistema=CTA.cod_sistema
LEFT JOIN ${esquema_cd}.cd_cap_relacion_cliente FIN on
	CTA.id_cliente = FIN.id_cliente_finacle AND FIN.cod_sistema=CTA.cod_sistema
LEFT JOIN ${esquema_cu}.cu_cap_cat_familia_producto PRD on
	CTA.cod_producto = PRD.cod_producto
    and CTA.id_cuenta = PRD.id_cuenta
LEFT JOIN ${esquema_cu}.cu_cap_saldos_disponibles_ctas SLD on
	CTA.id_cuenta = SLD.id_cuenta
;

COMPUTE STATS ${esquema_cu}.cu_cap_portafolio_cuentas_activas;
