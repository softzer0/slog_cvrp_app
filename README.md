## Solve Logistics CVRP/TSP backend app

### Development
* Starting up the server:
  1. Go to the `docker/dev` directory 
  2. If you're doing initialization, execute first: `docker-compose run app docker/wait-for-postgres.sh db "flask db migrate && flask db reset"`
  3. * Run it in isolated Docker environment using: `docker-compose up`
     * Add `-d` parameter if you want to run it in the background
* Default initial user and other seeds are located in `db/seeds.py` file
* Generating migrations (if in Docker then run in `app` container):
  * `flask db migrate revision --autogenerate`
  * If you want to name it, just pass `-m` parameter with the message following it in quotes
* For a complete DB reset, note that applying migrations (present in initialization command above) needs to be run first on an empty DB, and then it can be reset, which along the way runs seeding, too