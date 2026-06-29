-- ___________________________________________________________________________________________________________________________________
--/     #####   PROYECTO CRYSTAL DATA   #####
--| @FECHA DE CREACION:
--|     # Martes, 24 de Febrero del 2026
--| @DOMINIOS:                          
--|     # Captacion
--| @ARCHIVO:                           
--|     # 01_cd_cap_cuenta_deltSLD.sql 
--| @AUTOR:                                     
--|     # Erick Suarez Buendia <erick.suarez@algorithia.com>
--|	# Brenda Sarahi Rosas Morán <brendSLD.rosasm@algorithia.com>
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
--|     # ${fec_ini_sem} = 2026-04-27
--\____________________________________________________________________________________________________________________________________/

INVALIDATE METADATA ws_ec_cu_baz_bdclientes.cu_finacle_saldos_decrypt;
REFRESH ws_ec_cu_baz_bdclientes.cu_finacle_saldos_decrypt;
COMPUTE STATS ws_ec_cu_baz_bdclientes.cu_finacle_saldos_decrypt;

INSERT OVERWRITE TABLE ${esquema_cu}.cu_cap_universo_cuentas  
PARTITION(COD_SISTEMA)
SELECT 
         id_cliente                                      AS id_cliente
        ,CAST(CTA.sucursalapertura AS string)            AS ID_SUCURSAL_APERTURA
        ,SLD.ID_CUENTA
        ,TO_DATE(SLD.fechaapertura)                      AS FEC_APERTURA
        ,fechacancelacion                                AS FEC_CANCELACION
        ,CAST(SLD.centrocontable AS string)              AS ID_SUCURSAL_GESTORA
        ,trim(SLD.prod_subprod)                          AS COD_PRODUCTO
        ,SLD.fechaultimomovimiento                       AS FEC_ULTIMA_TXN
        ,CAST(PF9.numero_ultima_txn AS INT)              AS NUM_ULTIMA_TXN
        ,CAST(CTA.sucursal AS string)                    AS ID_SUCURSAL_ULTIMA_TXN
        ,CAST(CTA.usuario AS string)                     AS COD_USUARIO_ULTIMA_TXN
        ,IF(CTA.tipobloqueo IS NULL OR TRIM(CTA.tipobloqueo)='','SIN BLOQUEO','BLOQUEADA')     AS COD_BLOQUEO
        ,"T-TITULAR"                                                                           AS DESC_COD_TITULAR
        ,CASE WHEN SLD.personalidad ='301' THEN 'PF'
              WHEN SLD.personalidad ='721' THEN 'PM'
                 ELSE ''
            END                                           AS COD_TIPO_PERSONA
        ,CASE 
			WHEN trim(SLD.estatuscuenta)='A' THEN 'ACTIVA'
			WHEN trim(SLD.estatuscuenta)='C' THEN 'CANCELADA'
			ELSE SLD.estatuscuenta
		END AS COD_ESTATUS
        ,CAST(SLD.moneda AS string) 					  AS COD_TIPO_MONEDA 
        ,CAST(SLD.saldototal AS DECIMAL(32,2) )           AS SLD_ACTUAL 
        ,DATEDIFF(now(), SLD.fechaultimomovimiento)       AS num_dias_inactividad 
        ,CAST(plazodeposito AS STRING) as plazodeposito
        /*,case 
        when concat(CAST(YEAR(SLD.fechaapertura) as string),
                CAST(WEEK(SLD.fechaapertura) as string)) 
                        between concat(CAST(YEAR(now()) as string)
                        ,CAST ((WEEK(DATE_ADD(now(),-7))) as string)) and concat(CAST(YEAR(now()) as string),CAST ((WEEK(now())) as string)) then 1
        end                                                                     as ind_cuenta_nueva
        */
        ,CASE
		    WHEN SLD.fechaapertura >= DATE_ADD(NOW(), -7)
		     AND SLD.fechaapertura < NOW()
		    THEN 1
		    ELSE 0
		END AS ind_cuenta_nueva
        ,DATEDIFF(now(), SLD.fechaapertura)                                       as num_dias_antiguedad
        ,CURRENT_TIMESTAMP()                                                    AS FEC_CARGA
        ,'FINACLE'                                                               AS COD_SISTEMA 
FROM (
        SELECT 
             id_cliente
            ,id_cuenta
            ,cta_encrypt 
            ,from_unixtime(cast(round(fechaapertura/1000,0) as BIGINT),"yyyy-MM-dd HH:mm:ss") as fechaapertura 
            ,from_unixtime(cast(round(fechacancelacion/1000,0) as BIGINT),"yyyy-MM-dd HH:mm:ss") as fechacancelacion 
            ,centrocontable  
            ,from_unixtime(cast(round(fechaultimomovimiento/1000,0) as BIGINT),"yyyy-MM-dd HH:mm:ss") as fechaultimomovimiento 
            ,personalidad 
            ,estatuscuenta 
            ,moneda 
            ,saldototal
            ,plazodeposito
            ,CONCAT(SUBSTRING(producto, 1, 2),'-',LPAD(SUBSTRING(producto, 3), 4, '0')) AS prod_subprod
        FROM ws_ec_cu_baz_bdclientes.cu_finacle_saldos_decrypt
    ) AS SLD
LEFT JOIN(
        SELECT *
        FROM(
            SELECT 
                 numerocuenta 
                ,sucursalapertura 
                ,sucursal 
                ,usuario 
                ,tipobloqueo
                ,ROW_NUMBER() OVER(PARTITION BY numerocuenta ORDER BY fechacambio ASC ) AS ultimo_reg
            FROM rd_baz_bdclientes.rd_fin_cuentav2  
            WHERE to_date(from_unixtime(unix_timestamp(trim(cast(fifecha as string)), 'yyyyMMdd'))) <= '${fec_ini_sem}'
    		) AS A
    	WHERE ultimo_reg=1
		) AS CTA ON
    SLD.cta_encrypt = CTA.numerocuenta
LEFT JOIN(
        SELECT 
             cuenta
            ,count(*) as numero_ultima_txn
        FROM rd_baz_bdclientes.rd_fin_990pf
        --WHERE to_date(from_unixtime(unix_timestamp(trim(cast(fifecha as string)), 'yyyyMMdd'))) <= '${fec_ini_sem}' -- por cambio en horario de ingesta de la cuenta_v2
        GROUP BY 1
	) AS PF9 ON
    SLD.cta_encrypt = PF9.cuenta
;

COMPUTE STATS ${esquema_cu}.cu_cap_universo_cuentas;