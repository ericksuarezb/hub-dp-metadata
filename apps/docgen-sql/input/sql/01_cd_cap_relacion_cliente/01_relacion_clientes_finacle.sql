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
--|     # 
--\____________________________________________________________________________________________________________________________________/

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_relacion_cliente_finacle
SELECT 
     id_cliente_alnova 
    ,id_cliente_finacle
    ,id_cliente_unico
    ,id_icu_digital
    ,id_conversion
    ,fec_ult_mod_cte_unico
    ,CURRENT_TIMESTAMP() AS fec_carga
    ,'FINACLE' as cod_sistema
FROM(
    SELECT
         t0.fiid_cliente_unico AS id_conversion
        ,t0.fccliente_cif      AS id_cliente_finacle
        ,NULLIF(
            TRIM(CONCAT_WS('-',
            CAST(t1.fipais AS STRING),
            CAST(t1.ficanal AS STRING),
            CAST(t1.fisucursal AS STRING),
            CAST(t1.fifolio AS STRING)
            )), '' ) AS id_cliente_unico
        ,IFNULL(t2.t065_num_cus, t3.fccliente_alnova) AS id_cliente_alnova
        ,t4.t403_bdmid AS id_icu_digital
        ,ROW_NUMBER() OVER (
            PARTITION BY t0.fccliente_cif
            ORDER BY
                IF(t1.fifolio IS NOT NULL, 1, 0) + IF(t2.t065_num_cus IS NOT NULL, 1, 0) DESC
                , IF(t4.t403_bdmid IS NOT NULL, 1, 0) DESC
                , IF(t3.fccliente_alnova = t2.t065_num_cus, 1, 0) DESC
                , t0.fdfecha_alta DESC, t3.fdfecha_alta DESC
                , t2.t065_stp_last_mod DESC
        ) AS prioridad
        ,t065_stp_last_mod as fec_ult_mod_cte_unico
    FROM rd_baz_bdclientes.rd_tacuctefinacle t0
    LEFT JOIN tmp_baz_bdclientes.rd_cenconversion_clienteunico t1 ON 
        t0.fiid_cliente_unico = CAST(t1.fiid_cliente_unico AS INT)
    LEFT JOIN rd_baz_bdclientes.rd_pedt065 t2 ON 
        t1.fipais   = t2.t065_acc_country
    AND t1.ficanal   = t2.t065_acc_channel
    AND t1.fisucursal = t2.t065_acc_brn
    AND t1.fifolio   = t2.t065_acc_folio
    LEFT JOIN rd_baz_bdclientes.rd_cencuentaperson_clienteunico t3 ON 
        t3.fiid_cliente_unico = CAST(t1.fiid_cliente_unico AS INT)
    LEFT JOIN (
        SELECT 
             t403_num_clte
            ,t403_bdmid
        FROM (
            SELECT 
                 t403_num_clte
                ,t403_bdmid
                ,ROW_NUMBER() OVER (PARTITION BY t403_num_clte ORDER BY t403_stp_ultmod DESC) AS rn
            FROM rd_baz_bdclientes.rd_mcdt403
            ) x
        WHERE rn = 1
        ) t4 ON 
    IFNULL(t2.t065_num_cus, t3.fccliente_alnova) = t4.t403_num_clte
    ) A
WHERE prioridad = 1
;

compute stats ${esquema_cu}.cu_cap_relacion_cliente_finacle;




