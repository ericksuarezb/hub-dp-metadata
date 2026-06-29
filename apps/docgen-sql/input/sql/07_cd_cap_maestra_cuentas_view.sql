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
--| # Brenda Sarahi Rosas Morán <brenda.rosasm@algorithia.com>
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
--|     # ${num_periodo_2_sem_atras} = 202615
--\____________________________________________________________________________________________________________________________________/

DROP TABLE IF EXISTS ${esquema_cd}.cd_cap_maestro_cuentas;
CREATE TABLE ${esquema_cd}.cd_cap_maestro_cuentas STORED AS PARQUET AS 
SELECT 
 DISTINCT
     COALESCE(ALN.id_master ,FIN.id_master,-CAST(ALN.id_cliente_alnova AS BIGINT),-CAST(FIN.id_cliente_finacle AS BIGINT)) AS id_master 
    ,CTA.id_cliente_alnova
    ,CTA.id_cliente_finacle
    ,CTA.id_cliente_unico
    ,CTA.id_icu_digital
    ,CTA.cod_tipo_persona
    ,CTA.cod_tipo_moneda
    ,CTA.id_cuenta
    ,IFNULL(SUC2.t078_centro_6, CTA.id_sucursal_apertura) AS id_sucursal_apertura
    ,IFNULL(SUC3.t078_centro_6, CTA.id_sucursal_gestora)  AS id_sucursal_gestora    
    ,CTA.desc_cod_titular
    ,CTA.cod_estatus
    ,CTA.fec_apertura
    ,CASE 
        WHEN MONTH(fec_apertura) = 1 AND WEEKOFYEAR(fec_apertura) >= 50   -- DIC/ENE
            THEN 
                CAST(CONCAT (
                        CAST(YEAR(fec_apertura) - 1 AS STRING)
                        ,LPAD(CAST(WEEKOFYEAR(fec_apertura) AS STRING), 2, '0')
                        ) AS INT)
        WHEN MONTH(fec_apertura) = 12 AND WEEKOFYEAR(fec_apertura) = 1    -- ENE/DIC
            THEN 
                CAST(CONCAT (
                        CAST(YEAR(fec_apertura) + 1 AS STRING)
                        ,LPAD(CAST(WEEKOFYEAR(fec_apertura) AS STRING), 2, '0')
                        ) AS INT)
            ELSE 
                CAST(CONCAT (
                    CAST(YEAR(fec_apertura) AS STRING)
                    ,LPAD(CAST(WEEKOFYEAR(fec_apertura) AS STRING), 2, '0')
                    ) AS INT)
        END AS num_sem_apertura 
    ,CTA.cod_bloqueo
    ,CTA.fec_ultima_txn
    ,IFNULL(SUC4.t078_centro_6,CTA.id_sucursal_ultima_txn )  AS id_sucursal_ultima_txn
    ,CTA.cod_usuario_ultima_txn
    ,CTA.num_ultima_txn
    ,NULLIFZERO(CAST(TRIM(POR.id_empleado) AS INT)) AS id_empleado_portafolio
    ,TRIM(POR.tipo_relacion) AS cod_relacion_portafolio
    ,IFNULL(SUC1.t078_centro_6, POR.id_sucursal_asignada_aux) AS id_sucursal_portafolio  
    ,CTA.cod_producto
    ,CTA.cod_nivel_cuenta
    ,CTA.cod_producto_nivel_01
    ,CTA.cod_producto_nivel_02
    ,CTA.cod_producto_nivel_03
    ,CTA.cod_producto_nivel_04
    ,CTA.cod_producto_nivel_05
    ,CTA.cod_producto_nivel_06
    ,CTA.cod_producto_nivel_07
    ,CTA.sld_actual
    ,CTA.sld_disponible
    ,CTA.cod_sld_disponible
    ,CTA.fec_carga
    ,CTA.cod_sistema
    /*
    ,CASE 
	  WHEN weekofyear(date_add(now(),-1)) = 1  AND month(date_add(now(),-1)) = 12 THEN (year(date_add(now(),-1)) + 1)*100 + weekofyear(date_add(now(),-1))
	  WHEN weekofyear(date_add(now(),-1)) >=52 AND month(date_add(now(),-1)) = 1  THEN (year(date_add(now(),-1)) - 1)*100 + weekofyear(date_add(now(),-1))
	  ELSE year(date_add(now(),-1))*100+weekofyear(date_add(now(),-1))
	 END AS num_periodo_sem
     * 
     */
    ,202617 as num_periodo_sem
    ,IF(CTA.desc_cod_titular = "T-TITULAR" ,"T" ,"O") AS cod_titular
FROM ${esquema_cd}.cd_cap_portafolio_cuentas_activas CTA
LEFT JOIN (
  SELECT 
    cuenta_alnova
   ,id_empleado
   ,tipo_relacion
            ,IF(LENGTH(id_sucursal_asignada) < 4,LPAD(id_sucursal_asignada,4,'0'),id_sucursal_asignada) AS id_sucursal_asignada_aux
  FROM cu_baz_bdclientes.cu_portafolio_fenix_analitica_crm_historica 
  WHERE semanaproceso = ${num_periodo_2_sem_atras}
 ) POR on
CTA.id_cuenta = POR.cuenta_alnova
LEFT JOIN rd_baz_bdsopoperlog.rd_tcdt078 SUC1 ON
 POR.id_sucursal_asignada_aux = SUC1.t078_centro_4  
 
LEFT JOIN rd_baz_bdsopoperlog.rd_tcdt078 SUC2 ON
 CTA.id_sucursal_apertura     = SUC2.t078_centro_4 
 
LEFT JOIN rd_baz_bdsopoperlog.rd_tcdt078 SUC3 ON
 CTA.id_sucursal_gestora      = SUC3.t078_centro_4 
 
LEFT JOIN rd_baz_bdsopoperlog.rd_tcdt078 SUC4 ON
 CTA.id_sucursal_ultima_txn   = SUC4.t078_centro_4 
 
LEFT JOIN ${esquema_cd}.cd_cap_relacion_cliente ALN ON
 (CTA.id_cliente_alnova=ALN.id_cliente_alnova AND ALN.cod_sistema='ALNOVA')
LEFT JOIN ${esquema_cd}.cd_cap_relacion_cliente FIN ON
 (CTA.id_cliente_finacle=FIN.id_cliente_finacle AND FIN.cod_sistema='FINACLE')
;

COMPUTE STATS ${esquema_cu}.cu_cap_portafolio_cuentas_activas;