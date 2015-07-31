% include('templates/header.tpl', title='Series',
%         stylesheets=('series-index.css', ))
% if len(series) > 0:
<table class="table table-condensed table-striped">
    <tr>
        <th>Status</th>
        <th>Subject</th>
        <th>Author</th>
        <th>Age</th>
    </tr>
    % for s in series:
        <tr>
            <td>
                %if s.get('reviewed'):
                    <span title="Reviewed by {{", ".join([x for x, y in s['reviewers']])}}" class="label label-success">R</span>
                %end
                %if s.get('can-apply') == True:
                    <a href="{{s.get('git-url')}}" target="blank"><span class="label label-info">G</span></a>
                %elif s.get('can-apply') == False:
                    <span title="Series doesn't apply to current master" class="label label-default">N</span>
                %end
                %if s.get('obsoleted-by'):
                    <a href="/series/{{uri(s['obsoleted-by'])}}">
                        <span title="Old version, obsoleted by: {{s['obsoleted-by-subject']}}" class="label label-default">O</span>
                    </a>
                %elif s['testings-failed']:
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="Failed tests: {{ ", ".join([x for x, y in s.get('testings-failed')]) }}" class="label label-danger">E</span>
                    </a>
                %elif s['testings-warning']:
                    <a href="/testing/log/{{uri(s['message-id'])}}">
                        <span title="There are warnings in tests: {{ ", ".join([x for x, y in s.get('testings-warning')]) }}" class="label label-warning">W</span>
                    </a>
                %end
            </td>
            <td>
                <a id="{{s['message-id']}}" href="/series/{{uri(s['message-id'])}}">{{s['subject']}}</a>
            </td>
            <td><span title="{{s['author-address']}}">{{s['author']}}</span></td>
            <td><span class="timestamp" title="{{s['date']}}">{{s['age']}}</span></td>
        </tr>
    %end
</table>

% else:
    <div id="message">
      <p>No patches found.</p>
      <div class="frownie">:(</div>
    </div>
%end

<nav>
    <ul class="pagination">
        %dot = True
        %for i in range(0, totalpages):
            % between = lambda v, s, e: v >= s and v <= e
            % show = between(i, 0, 9)
            % show = show or between(i, totalpages - 5, totalpages - 1)
            % show = show or between(i, curpage - 2, curpage + 3)
            % if show:
                <li class="{{"active" if curpage == i else ""}}">
                    <a href="/index/{{i * pagesize}}-{{(i + 1) * pagesize}}{{"?search="+search if search else ""}}">{{i + 1}}</a>
                </li>
                %dot = True
            %elif dot:
                <li class="disabled">
                    <a href="#">...</a>
                </li>
                %dot = False
            %end
        %end
    </ul>
</nav>


<script type="text/javascript">

function main() {
    $(".timestamp").each(function (i, o) {
        $(o).attr("title", new Date(1000 * $(o).attr("title")));
    });
}

$(main);

</script>
% include('templates/footer.tpl')
