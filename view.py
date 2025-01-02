
@celery.task(name='tasks.pushpost')
def pushpost(task_data):
    logger.info(f"Task received: {task_data}")
    driver = None
    try:
        # Ensure the task runs within the Flask application context
        with app.app_context():
            # Fetch the task
            task = Task.query.get(task_data['task_id'])
            if not task:
                logger.error(f"Task {task_data['task_id']} not found")
                return False

            # Fetch the associated account
            account = Account.query.get(task_data['account_id'])
            if not account:
                logger.error(f"Account {task_data['account_id']} not found")
                task.status = 'failed'
                db.session.commit()
                return False

            task.status = 'processing'
            task.completed_at = datetime.utcnow()
            db.session.commit()

            # Get working proxy
            proxy_manager = ProxyManager(logger)
            proxy_result = proxy_manager.get_working_proxy()
            if proxy_result["code"] != 200:
                logger.error("No working proxy found")
                task.status = 'failed'
                db.session.commit()
                return False

            logger.info(f"Working proxy found: {proxy_result['data']}")

            # Start AdsPower browser
            user_id = account.user_id  # Use user_id from the account
            if not user_id:
                logger.error("No user_id found in account")
                task.status = 'failed'
                db.session.commit()
                return False

            proxy_config = {
                "proxy_soft": "other",
                "proxy_type": "socks5",
                "proxy_host": proxy_result['data'].split(':')[0],
                "proxy_port": proxy_result['data'].split(':')[1],
                "proxy_user": proxy_result['data'].split(':')[2],
                "proxy_password": proxy_result['data'].split(':')[3]
            }

            adspower_manager = AdsPowerManager(Config.ADSPOWER_API_KEY, logger)
            driver = adspower_manager.open_browser(user_id, proxy_config)
            if not driver:
                logger.error(f"Failed to open browser for profile: {user_id}")
                task.status = 'failed'
                db.session.commit()
                return False

            expected_country = account.country
            logger.info(f"expected country {expected_country}")

            if not adspower_manager.verify_proxy(driver, expected_country):
                logger.error("Proxy verification failed")
                task.status = 'failed'
                db.session.commit()
                return False

            # Task Here 
            result = task()

            logger.info(f"result : {result}")
            task.message = result["message"]
            task.status = 'completed' if result["status"] in [1, 3] else 'failed'
            task.task_output = result["data"]
            db.session.commit()

            return True

    except Exception as e:
        logger.error(f"Error processing task {task_data['task_id']}: {e}")
        if task:
            task.status = 'failed'
            db.session.commit()
        return False

    finally:
        try:
            if driver:
                try:
                    driver.current_url
                    logger.info("Selenium driver is active, quitting...")
                    driver.quit()
                except Exception as e:
                    logger.warning(f"Driver was unresponsive: {e}")

            browser_status = adspower_manager.check_browser_status(user_id)
            if browser_status and browser_status.get("code") == 0:
                    logger.info("Closing AdsPower browser...")
                    close_response = adspower_manager.close_browser(user_id)
                    
                    if not close_response or close_response.get("code") != 0:
                        logger.warning("Normal close failed, attempting force close...")
                        adspower_manager.close_browser(user_id)

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        logger.info("Task cleanup completed")
