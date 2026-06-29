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
--|     # ${esquema_cu} = ws_ec_cu_baz_bdclientes
--|     # ${esquema_cd} = ws_ec_cd_baz_bdclientes
--\____________________________________________________________________________________________________________________________________/

INSERT OVERWRITE TABLE ${esquema_cd}.cd_cap_relacion_cliente
WITH 
_id_master_alnova_ AS (
    SELECT
         ID_CLIENTE
        ,MIN(ID_MASTER) AS ID_MASTER
	FROM cd_baz_bdclientes.cd_cte_master_diaria
	WHERE COD_TIPO_CLIENTE IN('CLIENTE_ALNOVA')
	GROUP BY ID_CLIENTE
	), 
_id_master_finacle_ AS (
    SELECT
         ID_CLIENTE
        ,MIN(ID_MASTER) AS ID_MASTER
    FROM cd_baz_bdclientes.cd_cte_master_diaria
    WHERE COD_TIPO_CLIENTE IN('CLIENTE_FINACLE')
    GROUP BY ID_CLIENTE
	), 
_id_master_cu_ AS (
	SELECT
         ID_CLIENTE
        ,MIN(ID_MASTER) AS ID_MASTER
    FROM cd_baz_bdclientes.cd_cte_master_diaria
    WHERE COD_TIPO_CLIENTE IN('CLIENTE_UNICO')
    GROUP BY ID_CLIENTE
	), 
_id_master_icu_ AS (
	SELECT
         ID_CLIENTE
        ,MIN(ID_MASTER) AS ID_MASTER
    FROM cd_baz_bdclientes.cd_cte_master_diaria
    WHERE COD_TIPO_CLIENTE IN('CLIENTE_ICU')
    GROUP BY ID_CLIENTE
	)
SELECT 
     COALESCE(ALN.id_master ,FIN.id_master ,CU.id_master ,ICU.id_master, -CAST( IF(cod_sistema="ALNOVA", CTE.id_cliente_alnova, CTE.id_cliente_finacle) AS INT  )) AS id_master
    ,CTE.id_cliente_alnova 
    ,CTE.id_cliente_finacle
    ,CTE.id_cliente_unico
    ,CTE.id_icu_digital
    ,CTE.id_conversion
    ,CTE.fec_ult_mod_cte_unico
    ,CURRENT_TIMESTAMP() AS fec_carga
    ,cod_sistema
FROM(
    select id_cliente_alnova ,id_cliente_finacle ,id_cliente_unico ,id_icu_digital ,id_conversion ,fec_ult_mod_cte_unico ,cod_sistema
    from(
        select *
        from(
            select *
            from ${esquema_cu}.cu_cap_relacion_cliente_finacle 
            union all
            select *
            from ${esquema_cu}.cu_cap_relacion_cliente_alnova
            ) a
        ) b
    )CTE
LEFT JOIN _id_master_alnova_ ALN on
    CTE.id_cliente_alnova = ALN.id_cliente
LEFT JOIN _id_master_finacle_ FIN on
    CTE.id_cliente_finacle = FIN.id_cliente
LEFT JOIN _id_master_cu_ CU on
    CTE.id_cliente_unico = CU.id_cliente
LEFT JOIN _id_master_icu_ ICU on
    CTE.id_icu_digital = ICU.id_cliente
;

compute stats ${esquema_cd}.cd_cap_relacion_cliente;


